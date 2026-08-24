"""Read persisted telemetry in causal replay order without reopening a source file."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timezone
from typing import Iterator
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tractor_usage.application.contracts import NotFoundError, TelemetryImport
from tractor_usage.infrastructure.models import (
    TelemetryImportRecord,
    TelemetryMissionRecord,
    TelemetrySampleRecord,
)
from tractor_usage.infrastructure.telemetry_repository import _import
from tractor_usage.streaming.replay import RAW_SIGNAL_FIELDS, TelemetrySample


@dataclass(frozen=True)
class ReplayPreflight:
    telemetry_import: TelemetryImport
    mission_index: int | None
    sample_count: int


class PostgresTelemetryReplay:
    def __init__(self, session: Session, import_id: str, *, mission_index: int | None = None) -> None:
        self._session = session
        self._import_id = UUID(import_id)
        self._mission_index = mission_index

    def preflight(self) -> ReplayPreflight:
        record = self._session.get(TelemetryImportRecord, self._import_id)
        if record is None:
            raise NotFoundError("telemetry import not found")
        statement = select(func.count()).select_from(TelemetrySampleRecord).where(
            TelemetrySampleRecord.import_id == record.id
        )
        if self._mission_index is not None:
            statement = statement.where(TelemetrySampleRecord.mission_index == self._mission_index)
        sample_count = int(self._session.scalar(statement) or 0)
        if sample_count == 0:
            raise NotFoundError("telemetry mission has no samples")
        return ReplayPreflight(
            telemetry_import=_import(record),
            mission_index=self._mission_index,
            sample_count=sample_count,
        )

    def iter_samples(self) -> Iterator[TelemetrySample]:
        statement = (
            select(TelemetrySampleRecord, TelemetryMissionRecord)
            .join(
                TelemetryMissionRecord,
                (TelemetrySampleRecord.import_id == TelemetryMissionRecord.import_id)
                & (TelemetrySampleRecord.mission_index == TelemetryMissionRecord.mission_index),
            )
            .where(TelemetrySampleRecord.import_id == self._import_id)
            .order_by(
                TelemetrySampleRecord.mission_index,
                TelemetrySampleRecord.position_deciseconds,
            )
        )
        if self._mission_index is not None:
            statement = statement.where(TelemetrySampleRecord.mission_index == self._mission_index)
        statement = statement.execution_options(yield_per=5_000)
        record = self._session.get(TelemetryImportRecord, self._import_id)
        if record is None:
            raise NotFoundError("telemetry import not found")
        for sample, mission in self._session.execute(statement):
            yield _telemetry_sample(sample, mission, str(record.tractor_id))

    def iter_window_samples(
        self, *, mission_index: int, window_index: int
    ) -> Iterator[TelemetrySample]:
        """Yield one persisted causal window plus its immediately preceding sample."""

        if mission_index < 0 or window_index < 0:
            raise ValueError("mission_index and window_index must be non-negative")
        record = self._session.get(TelemetryImportRecord, self._import_id)
        if record is None:
            raise NotFoundError("telemetry import not found")
        mission = self._session.get(
            TelemetryMissionRecord,
            {"import_id": self._import_id, "mission_index": mission_index},
        )
        if mission is None:
            raise NotFoundError("telemetry mission not found")

        window_start = mission.origin_position_deciseconds + window_index * 600
        window_end = window_start + 600
        predecessor = self._session.scalar(
            select(TelemetrySampleRecord)
            .where(
                TelemetrySampleRecord.import_id == self._import_id,
                TelemetrySampleRecord.mission_index == mission_index,
                TelemetrySampleRecord.position_deciseconds < window_start,
            )
            .order_by(TelemetrySampleRecord.position_deciseconds.desc())
            .limit(1)
        )
        current = tuple(
            self._session.scalars(
                select(TelemetrySampleRecord)
                .where(
                    TelemetrySampleRecord.import_id == self._import_id,
                    TelemetrySampleRecord.mission_index == mission_index,
                    TelemetrySampleRecord.position_deciseconds >= window_start,
                    TelemetrySampleRecord.position_deciseconds < window_end,
                )
                .order_by(TelemetrySampleRecord.position_deciseconds)
            )
        )
        samples = ((predecessor,) if predecessor is not None else ()) + current
        for sample in samples:
            yield _telemetry_sample(sample, mission, str(record.tractor_id))


def replay_source_reference(telemetry_import: TelemetryImport) -> str:
    return (
        f"postgresql:telemetry-import:{telemetry_import.id}"
        f"#sha256={telemetry_import.semantic_sha256}"
    )


def _telemetry_sample(
    sample: TelemetrySampleRecord,
    mission: TelemetryMissionRecord,
    tractor_id: str,
) -> TelemetrySample:
    values = {field: getattr(sample, field) for field in RAW_SIGNAL_FIELDS}
    return TelemetrySample(
        tractor_id=tractor_id,
        mission_index=sample.mission_index,
        mission_elapsed_seconds=(
            sample.position_deciseconds - mission.origin_position_deciseconds
        ) / 10.0,
        position_seconds=sample.position_deciseconds / 10.0,
        source_row=sample.source_row,
        observed_at_utc=sample.observed_at_utc.astimezone(timezone.utc),
        **values,
    )
