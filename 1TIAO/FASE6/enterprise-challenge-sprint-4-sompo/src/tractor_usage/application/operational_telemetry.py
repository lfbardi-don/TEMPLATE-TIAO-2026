"""Small, bounded CSV intake using the same causal derivation and frozen inference."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from io import StringIO
import json
import math
from typing import Literal
from uuid import UUID, uuid4

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tractor_usage.application.contracts import (
    ConflictError, NotFoundError, PersistedTelemetrySample, TelemetryImport,
    TelemetryMission, WindowProvenance,
)
from tractor_usage.application.ports import UsageModel
from tractor_usage.application.use_cases import _fingerprint, _idempotency_key
from tractor_usage.infrastructure.models import TelemetryImportRecord, TelemetryMissionRecord, TractorRecord, ScoredWindowRecord
from tractor_usage.infrastructure.postgres_telemetry_replay import replay_source_reference
from tractor_usage.infrastructure.repositories import PostgresInspectionRepository
from tractor_usage.infrastructure.telemetry_repository import PostgresTelemetryRepository
from tractor_usage.infrastructure.window_mapping import complete_window_from_build_result
from tractor_usage.streaming.replay import RAW_SIGNAL_FIELDS, TelemetrySample
from tractor_usage.streaming.windows import CausalWindowAggregator, SIGNAL_RANGES, WindowBuildResult

MAX_CSV_BYTES = 12_000_000
MAX_CSV_ROWS = 20_000
CSV_COLUMNS = ("observed_at_utc", "mission_index", *RAW_SIGNAL_FIELDS)
REFERENCE_LABEL = "Referência Fendt 314 do modelo treinado; comparação demonstrativa para máquinas simuladas."
IntakeKind = Literal["simulated_csv", "operational_csv"]
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


@dataclass(frozen=True)
class ParsedTelemetry:
    samples: tuple[TelemetrySample, ...]
    windows: tuple[WindowBuildResult, ...]
    source_sha256: str
    semantic_sha256: str
    source_size_bytes: int

    def preview(self, source_kind: str) -> dict:
        return {
            "sample_count": len(self.samples),
            "mission_count": len({sample.mission_index for sample in self.samples}),
            "started_at_utc": self.samples[0].observed_at_utc.isoformat(),
            "ended_at_utc": self.samples[-1].observed_at_utc.isoformat(),
            "ready_window_count": sum(window.status == "READY" for window in self.windows),
            "skipped_window_count": sum(window.status == "NO_DATA" for window in self.windows),
            "source_kind": source_kind,
            "reference_label": REFERENCE_LABEL,
        }


def _csv_rows(csv_text: str):
    try:
        reader = csv.DictReader(StringIO(csv_text.lstrip("\ufeff")))
        if reader.fieldnames is None or len(reader.fieldnames) != len(CSV_COLUMNS) or set(reader.fieldnames) != set(CSV_COLUMNS):
            raise ValueError("Colunas esperadas: " + ", ".join(CSV_COLUMNS))
        yield from reader
    except csv.Error as error:
        raise ValueError(
            "Não foi possível ler o CSV. Verifique a formatação e o tamanho dos campos."
        ) from error


def parse_operational_csv(csv_text: str, tractor_id: str, source_kind: IntakeKind) -> ParsedTelemetry:
    encoded = csv_text.encode("utf-8")
    if not encoded or len(encoded) > MAX_CSV_BYTES:
        raise ValueError("O CSV deve ter entre 1 byte e 12 MB.")
    samples: list[TelemetrySample] = []
    windows: list[WindowBuildResult] = []
    aggregator = CausalWindowAggregator()
    origin: datetime | None = None
    previous: TelemetrySample | None = None
    canonical = sha256(f"{tractor_id}|{source_kind}|operational-utc-1hz-v1\n".encode())
    for index, row in enumerate(_csv_rows(csv_text)):
        line = index + 2
        if index >= MAX_CSV_ROWS:
            raise ValueError("O CSV deve ter no máximo 20.000 amostras.")
        if None in row or any(value is None for value in row.values()):
            raise ValueError(f"Linha {line}: número de colunas inválido.")
        try:
            observed = datetime.fromisoformat(row["observed_at_utc"].replace("Z", "+00:00"))
            if observed.tzinfo is None or observed.utcoffset().total_seconds() != 0:
                raise ValueError("timestamp must be UTC")
            if observed < EPOCH or observed.microsecond != 0:
                raise ValueError("timestamp must be whole seconds after 1970")
            mission = int(row["mission_index"])
            if mission < 0 or mission > 2_147_483_647:
                raise ValueError("mission invalid")
        except (ValueError, OverflowError) as error:
            raise ValueError(f"Linha {line}: informe data UTC com segundos inteiros e missão inteira não negativa.") from error
        if previous is not None:
            if observed <= previous.observed_at_utc:
                raise ValueError(f"Linha {line}: datas devem crescer, sem segundos repetidos.")
            if mission < previous.mission_index:
                raise ValueError(f"Linha {line}: as missões devem estar em ordem crescente.")
            if mission == previous.mission_index and (observed - previous.observed_at_utc).total_seconds() != 1:
                raise ValueError(f"Linha {line}: mantenha 1 amostra por segundo; use nova missão após uma interrupção.")
        if previous is None or mission != previous.mission_index:
            origin = observed
        values = {}
        for name in RAW_SIGNAL_FIELDS:
            try:
                value = float(row[name])
            except ValueError as error:
                raise ValueError(f"Linha {line}: {name} deve ser numérico e preenchido.") from error
            low, high = SIGNAL_RANGES[name]
            if not math.isfinite(value) or not low <= value <= high:
                raise ValueError(f"Linha {line}: {name} deve estar entre {low:g} e {high:g}.")
            values[name] = value
        assert origin is not None
        sample = TelemetrySample(
            tractor_id=tractor_id, mission_index=mission,
            mission_elapsed_seconds=(observed - origin).total_seconds(),
            position_seconds=(observed - EPOCH).total_seconds(), source_row=index,
            observed_at_utc=pd.Timestamp(observed), **values,
        )
        canonical.update(json.dumps([observed.isoformat(), mission, *values.values()], separators=(",", ":")).encode())
        canonical.update(b"\n")
        windows.extend(aggregator.ingest(sample))
        samples.append(sample)
        previous = sample
    windows.extend(aggregator.flush())
    if not samples or not any(window.status == "READY" for window in windows):
        raise ValueError("O CSV precisa conter pelo menos uma janela utilizável de 60 segundos.")
    return ParsedTelemetry(tuple(samples), tuple(windows), sha256(encoded).hexdigest(), canonical.hexdigest(), len(encoded))


def validate_intake_tractor(session: Session, tractor_id: str, source_kind: IntakeKind, *, lock: bool = False) -> None:
    statement = select(TractorRecord).where(TractorRecord.id == UUID(tractor_id))
    if lock:
        statement = statement.with_for_update()
    if session.scalar(statement) is None:
        raise NotFoundError("tractor not found")
    kinds = set(session.scalars(select(TelemetryImportRecord.source_kind).where(TelemetryImportRecord.tractor_id == UUID(tractor_id))))
    if source_kind == "simulated_csv" and kinds - {"simulated_csv"}:
        raise ConflictError("Dados simulados devem usar uma máquina separada dos dados reais.")
    if source_kind == "operational_csv" and "observed_dataset_replay" not in kinds:
        raise ConflictError("A entrada real está habilitada apenas para a unidade Fendt 314 da referência observada; cadastre outras unidades como simulação.")


def validate_intake_period(session: Session, tractor_id: str, parsed: ParsedTelemetry) -> bool:
    duplicate = session.scalar(select(TelemetryImportRecord.id).where(TelemetryImportRecord.semantic_sha256 == parsed.semantic_sha256))
    if duplicate is not None:
        return True
    last = session.scalar(select(func.max(TelemetryImportRecord.ended_at_utc)).where(TelemetryImportRecord.tractor_id == UUID(tractor_id)))
    if last is not None and parsed.samples[0].observed_at_utc <= last:
        raise ConflictError("O período deve começar após o último dado importado. Reenvie o mesmo conteúdo para uma repetição sem duplicatas.")
    return False


def import_operational_csv(session: Session, model: UsageModel, *, tractor_id: str, file_name: str,
                           source_kind: IntakeKind, csv_text: str, worker_id: str) -> dict:
    parsed = parse_operational_csv(csv_text, tractor_id, source_kind)
    # The tractor row lock serializes imports. All samples and decisions commit together.
    validate_intake_tractor(session, tractor_id, source_kind, lock=True)
    existing = session.scalar(select(TelemetryImportRecord).where(TelemetryImportRecord.semantic_sha256 == parsed.semantic_sha256))
    if existing is not None:
        return import_summary(session, existing, duplicate=True)
    validate_intake_period(session, tractor_id, parsed)
    import_id = str(uuid4())
    data = TelemetryImport(
        id=import_id, tractor_id=tractor_id, dataset_split="operational", source_format="operational_csv",
        source_file_name=file_name, source_member=None, source_size_bytes=parsed.source_size_bytes,
        source_sha256=parsed.source_sha256, semantic_sha256=parsed.semantic_sha256,
        schema_version="fendt314-telemetry-v1", transform_version="operational-utc-1hz-v1", epoch_utc=EPOCH,
        sample_count=len(parsed.samples), mission_count=len({s.mission_index for s in parsed.samples}),
        started_at_utc=parsed.samples[0].observed_at_utc.to_pydatetime(),
        ended_at_utc=parsed.samples[-1].observed_at_utc.to_pydatetime(),
        created_at_utc=datetime.now(timezone.utc), source_kind=source_kind, imported_by_worker_id=worker_id,
    )
    groups: dict[int, list[TelemetrySample]] = {}
    for sample in parsed.samples:
        groups.setdefault(sample.mission_index, []).append(sample)
    missions = tuple(TelemetryMission(
        import_id=import_id, mission_index=mission,
        origin_position_deciseconds=round(items[0].position_seconds * 10),
        first_position_deciseconds=round(items[0].position_seconds * 10),
        last_position_deciseconds=round(items[-1].position_seconds * 10),
        first_source_row=items[0].source_row, last_source_row=items[-1].source_row,
        started_at_utc=items[0].observed_at_utc.to_pydatetime(), ended_at_utc=items[-1].observed_at_utc.to_pydatetime(),
        sample_count=len(items),
    ) for mission, items in groups.items())
    repository = PostgresTelemetryRepository(session)
    repository.create_import(data, missions)
    persisted = tuple(PersistedTelemetrySample(
        mission_index=sample.mission_index,
        mission_origin_position_deciseconds=round(groups[sample.mission_index][0].position_seconds * 10),
        position_deciseconds=round(sample.position_seconds * 10), source_row=sample.source_row,
        observed_at_utc=sample.observed_at_utc.to_pydatetime(), values={name: getattr(sample, name) for name in RAW_SIGNAL_FIELDS},
    ) for sample in parsed.samples)
    for start in range(0, len(persisted), 1000):
        repository.insert_samples(import_id, persisted[start:start + 1000])
    provenance = WindowProvenance(source_kind=source_kind, dataset_split="operational", source_reference=replay_source_reference(data))
    scoring = PostgresInspectionRepository(session)
    windows = tuple(complete_window_from_build_result(result, provenance=provenance, telemetry_import_id=import_id)
                    for result in parsed.windows if result.status == "READY")
    # Features are built only from the exact validated samples persisted above.
    batch_score = getattr(model, "score_many", None)
    decisions = batch_score(tractor_id, windows) if batch_score else tuple(model.score(tractor_id, window) for window in windows)
    for window, decision in zip(windows, decisions, strict=True):
        scoring.insert_window(tractor_id, window, decision, idempotency_key=_idempotency_key(model.model_version, tractor_id, window), fingerprint=_fingerprint(window))
    return import_summary(session, session.get(TelemetryImportRecord, UUID(import_id)))


def import_summary(session: Session, record: TelemetryImportRecord, *, duplicate: bool = False) -> dict:
    windows, physical, alerts = session.execute(select(
        func.count(), func.count().filter(ScoredWindowRecord.physical_eligible), func.count().filter(ScoredWindowRecord.hybrid_alert)
    ).where(ScoredWindowRecord.telemetry_import_id == record.id)).one()
    return {
        "id": str(record.id), "duplicate": duplicate, "file_name": record.source_file_name,
        "sample_count": record.sample_count, "mission_count": record.mission_count,
        "started_at_utc": record.started_at_utc, "ended_at_utc": record.ended_at_utc,
        "created_at_utc": record.created_at_utc, "source_kind": record.source_kind,
        "imported_by_worker_id": record.imported_by_worker_id,
        "ready_window_count": windows, "skipped_window_count": sum(0 < count % 60 < 55 for count in session.scalars(select(TelemetryMissionRecord.sample_count).where(TelemetryMissionRecord.import_id == record.id))) if record.dataset_split == "operational" else None,
        "window_count": windows, "physical_candidate_count": physical, "alert_count": alerts,
        "model_version": "fendt314-hybrid-v2.0.1", "reference_label": REFERENCE_LABEL,
    }
