from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import csv
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
from threading import Barrier
from uuid import UUID, uuid4

import pandas as pd
import pytest

DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
if not DATABASE_URL:
    pytest.skip("TEST_DATABASE_URL is not configured", allow_module_level=True)

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, func, select, text
from sqlalchemy.orm import Session

from tractor_usage.api.app import create_app
from tractor_usage.application.contracts import (
    CompleteWindow,
    ConflictError,
    CreateFleet,
    CreateTractor,
    PersistedTelemetrySample,
    ScoredDecision,
    TelemetryImport,
    TelemetryMission,
    WindowProvenance,
)
from tractor_usage.application.use_cases import CreateFleetUseCase, IngestWindowUseCase
from tractor_usage.application.telemetry import ImportTelemetryUseCase
from tractor_usage.infrastructure.frozen_model import FrozenBundleUsageModel
from tractor_usage.infrastructure.http_window_ingest import (
    HttpWindowIngestClient,
    ObservedReplayProvenance,
    WindowIngestHttpError,
    build_complete_window_payload,
)
from tractor_usage.infrastructure.models import (
    Base,
    FleetRecord,
    InspectionCaseRecord,
    ScoredWindowRecord,
    TelemetryImportRecord,
    TelemetryMissionRecord,
    TelemetrySampleRecord,
    TractorRecord,
)
from tractor_usage.infrastructure.postgres_telemetry_replay import (
    PostgresTelemetryReplay,
    replay_source_reference,
)
from tractor_usage.infrastructure.repositories import PostgresInspectionRepository
from tractor_usage.infrastructure.telemetry_repository import PostgresTelemetryRepository
from tractor_usage.infrastructure.window_mapping import complete_window_from_build_result
from tractor_usage.streaming.replay import (
    FENDT_314_EPOCH_UTC,
    RAW_SIGNAL_FIELDS,
    REPLAY_COLUMNS,
    TelemetrySample,
)
from tractor_usage.streaming.windows import CausalWindowAggregator, WindowBuildResult


UTC = timezone.utc


def _observed_sample(tractor_id: str, second: int) -> TelemetrySample:
    return TelemetrySample(
        tractor_id=tractor_id,
        mission_index=277,
        mission_elapsed_seconds=float(second),
        position_seconds=float(second),
        source_row=second,
        observed_at_utc=FENDT_314_EPOCH_UTC + pd.to_timedelta(second, unit="s"),
        engine_rpm=1200.0,
        actual_engine_torque_pct=50.0,
        engine_load_pct=80.0,
        accelerator_pct=20.0,
        coolant_temp_c=80.0,
        front_axle_speed_kph=5.0,
        speed_over_ground_mps=2.0,
        ground_implement_speed_mmps=2000.0,
        wheel_vehicle_speed_kph=7.2,
        rear_pto_rpm=500.0,
        rear_hitch_position=40.0,
        rear_hitch_in_work=1.0,
        rear_link_force_pct=10.0,
        rear_draft_n=1000.0,
        ground_machine_speed_mps=2.0,
        machine_selected_speed_mps=2.0,
        wheel_machine_speed_mps=2.5,
    )


class _ConcurrentModel:
    model_version = "fendt314-hybrid-v2.0.1"

    def score(self, tractor_id, window):
        return ScoredDecision(
            model_version=self.model_version,
            operational_regime=0,
            contextual_rarity_score=0.0,
            contextual_rarity_threshold=1.0,
            physical_eligible=False,
            physical_reasons=(),
            hybrid_alert=False,
            contextual_reasons=(),
        )


def _run_concurrently(engine, tractor_id: str, requests: tuple[CompleteWindow, ...]):
    barrier = Barrier(len(requests))

    def execute(request: CompleteWindow) -> str:
        with Session(engine) as session:
            use_case = IngestWindowUseCase(
                PostgresInspectionRepository(session), _ConcurrentModel()
            )
            barrier.wait(timeout=5)
            try:
                result = use_case.execute(tractor_id, request)
            except ConflictError:
                return "conflict"
            return "duplicate" if result.duplicate else "new"

    with ThreadPoolExecutor(max_workers=len(requests)) as executor:
        return tuple(executor.map(execute, requests))


def test_postgres_schema_enforces_atomic_fleet_registration() -> None:
    engine = create_engine(DATABASE_URL)
    fleet_name = f"atomic-fleet-{uuid4()}"
    try:
        Base.metadata.create_all(engine)
        with engine.connect() as connection:
            assert connection.execute(text("SELECT 1")).scalar_one() == 1
        with Session(engine) as session:
            repository = PostgresInspectionRepository(session)
            use_case = CreateFleetUseCase(repository)
            request = CreateFleet(
                name=fleet_name,
                tractors=(
                    CreateTractor(external_id="duplicate", display_name=None),
                    CreateTractor(external_id="duplicate", display_name=None),
                ),
            )
            with pytest.raises(ConflictError):
                use_case.execute(request)
            assert session.scalar(select(Base.metadata.tables["fleets"].c.id).where(
                Base.metadata.tables["fleets"].c.name == fleet_name
            )) is None
    finally:
        engine.dispose()


def test_concurrent_ingestion_serializes_idempotent_and_conflicting_requests() -> None:
    engine = create_engine(DATABASE_URL)
    fleet_id = None
    tractor_id = None
    telemetry_import_id = None
    try:
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            registration = CreateFleetUseCase(
                PostgresInspectionRepository(session)
            ).execute(
                CreateFleet(
                    name=f"concurrency-{uuid4()}",
                    tractors=(
                        CreateTractor(external_id="F314-concurrent", display_name=None),
                    ),
                )
            )
            fleet_id = registration.fleet.id
            tractor_id = registration.tractors[0].id

            import_id = str(uuid4())
            semantic_sha256 = "c" * 64
            imported_at = FENDT_314_EPOCH_UTC.to_pydatetime()
            replay_samples = tuple(
                _observed_sample(tractor_id, second) for second in range(121)
            )
            telemetry_import = TelemetryImport(
                id=import_id,
                tractor_id=tractor_id,
                dataset_split="validation",
                source_format="canonical_csv",
                source_file_name="concurrency-observed.csv",
                source_member=None,
                source_size_bytes=1,
                source_sha256="b" * 64,
                semantic_sha256=semantic_sha256,
                schema_version="fendt314-telemetry-v1",
                transform_version="canonical-pass-through-v1",
                epoch_utc=FENDT_314_EPOCH_UTC.to_pydatetime(),
                sample_count=len(replay_samples),
                mission_count=1,
                started_at_utc=imported_at,
                ended_at_utc=imported_at + timedelta(seconds=120),
                created_at_utc=imported_at,
            )
            missions = (
                TelemetryMission(
                    import_id=import_id,
                    mission_index=277,
                    origin_position_deciseconds=0,
                    first_position_deciseconds=0,
                    last_position_deciseconds=1200,
                    first_source_row=0,
                    last_source_row=120,
                    started_at_utc=imported_at,
                    ended_at_utc=imported_at + timedelta(seconds=120),
                    sample_count=len(replay_samples),
                ),
            )
            samples = tuple(
                PersistedTelemetrySample(
                    mission_index=sample.mission_index,
                    mission_origin_position_deciseconds=0,
                    position_deciseconds=int(sample.position_seconds * 10),
                    source_row=sample.source_row,
                    observed_at_utc=sample.observed_at_utc.to_pydatetime(),
                    values={field: getattr(sample, field) for field in RAW_SIGNAL_FIELDS},
                )
                for sample in replay_samples
            )
            telemetry_repository = PostgresTelemetryRepository(session)
            with telemetry_repository.transaction():
                telemetry_repository.create_import(telemetry_import, missions)
                telemetry_repository.insert_samples(import_id, samples)
            telemetry_import_id = import_id
            source_reference = f"postgresql:telemetry-import:{import_id}#sha256={semantic_sha256}"

        aggregator = CausalWindowAggregator()
        ready: dict[int, WindowBuildResult] = {}
        for sample in replay_samples:
            for result in aggregator.ingest(sample):
                if result.status == "READY":
                    ready[result.window_index] = result
        assert set(ready) == {0, 1}
        provenance = WindowProvenance(
            "observed_dataset_replay", "validation", source_reference
        )
        first = complete_window_from_build_result(
            ready[0], provenance=provenance, telemetry_import_id=telemetry_import_id
        )
        second = complete_window_from_build_result(
            ready[1], provenance=provenance, telemetry_import_id=telemetry_import_id
        )

        identical_results = _run_concurrently(engine, tractor_id, (first, first))
        assert sorted(identical_results) == ["duplicate", "new"]

        forged_second = replace(
            second,
            features={
                **second.features,
                "engine_rpm__mean": (second.features["engine_rpm__mean"] or 0.0) + 1.0,
            },
        )
        conflicting_results = _run_concurrently(
            engine,
            tractor_id,
            (second, forged_second),
        )
        assert sorted(conflicting_results) == ["conflict", "new"]

        with Session(engine) as session:
            stored = session.scalar(
                select(func.count())
                .select_from(ScoredWindowRecord)
                .where(ScoredWindowRecord.tractor_id == UUID(tractor_id))
            )
            assert stored == 2
            report_windows = PostgresInspectionRepository(session).list_report_windows(
                tractor_id,
                as_of_utc=imported_at + timedelta(seconds=90),
            )
            assert [window.window_index for window in report_windows] == [0]
    finally:
        if fleet_id is not None and tractor_id is not None:
            with Session(engine) as session, session.begin():
                session.execute(
                    delete(ScoredWindowRecord).where(
                        ScoredWindowRecord.tractor_id == UUID(tractor_id)
                    )
                )
                if telemetry_import_id is not None:
                    import_uuid = UUID(telemetry_import_id)
                    session.execute(delete(TelemetrySampleRecord).where(TelemetrySampleRecord.import_id == import_uuid))
                    session.execute(delete(TelemetryMissionRecord).where(TelemetryMissionRecord.import_id == import_uuid))
                    session.execute(delete(TelemetryImportRecord).where(TelemetryImportRecord.id == import_uuid))
                session.execute(
                    delete(TractorRecord).where(TractorRecord.id == UUID(tractor_id))
                )
                session.execute(
                    delete(FleetRecord).where(FleetRecord.id == UUID(fleet_id))
                )
        engine.dispose()


def test_persisted_telemetry_replay_periods_and_case_workflow(tmp_path: Path) -> None:
    engine = create_engine(DATABASE_URL)
    model_dir = Path(__file__).resolve().parents[2] / "models" / "fendt314-hybrid-v2.0.1"
    usage_model = FrozenBundleUsageModel.load(model_dir)
    fleet_id = None
    tractor_id = None
    telemetry_import_id = None
    source = tmp_path / "observed-validation.csv"
    source_row_origin = uuid4().int % 1_000_000_000
    # The source mission begins 30 seconds before the frozen validation split.
    # Its first persisted sample must therefore retain elapsed=30 instead of
    # pretending the split boundary is a new mission.
    observed_start = datetime(2024, 9, 7, 10, 17, 46, 200_000, tzinfo=UTC)
    start_deciseconds = round(
        (observed_start - FENDT_314_EPOCH_UTC.to_pydatetime()).total_seconds() * 10
    )
    template = _observed_sample("placeholder", 0)
    with source.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=REPLAY_COLUMNS)
        writer.writeheader()
        for second in range(150):
            position_deciseconds = start_deciseconds + second * 10
            writer.writerow(
                {
                    "mission_index": 277,
                    "position_seconds": f"{position_deciseconds / 10:.1f}",
                    "source_row": source_row_origin + second,
                    **{field: getattr(template, field) for field in RAW_SIGNAL_FIELDS},
                }
            )

    try:
        Base.metadata.create_all(engine)
        with TestClient(create_app(usage_model=usage_model, engine=engine)) as client:
            registration = client.post(
                "/v1/fleets",
                json={
                    "name": f"persisted-flow-{uuid4()}",
                    "tractors": [
                        {"external_id": f"F314-{uuid4()}", "display_name": "Persistido"}
                    ],
                },
            )
            assert registration.status_code == 201
            body = registration.json()
            fleet_id = body["fleet"]["id"]
            tractor_id = body["tractors"][0]["id"]

            with Session(engine) as session:
                importer = ImportTelemetryUseCase(PostgresTelemetryRepository(session))
                imported = importer.execute(
                    source=source,
                    tractor_id=tractor_id,
                    dataset_split="validation",
                    batch_size=17,
                )
                repeated = importer.execute(
                    source=source,
                    tractor_id=tractor_id,
                    dataset_split="validation",
                    batch_size=17,
                )
                telemetry_import_id = imported.telemetry_import.id
                assert imported.duplicate is False
                assert repeated.duplicate is True
                assert repeated.telemetry_import.id == telemetry_import_id

            periods = client.get(
                f"/v1/tractors/{tractor_id}/telemetry-periods",
                params={"import_id": telemetry_import_id},
            )
            assert periods.status_code == 200
            assert periods.json()["imports"][0]["sample_count"] == 120
            assert periods.json()["imports"][0]["missions"][0]["mission_index"] == 277

            with Session(engine) as session:
                replay = PostgresTelemetryReplay(
                    session, telemetry_import_id, mission_index=277
                )
                preflight = replay.preflight()
                samples = list(replay.iter_samples())
            assert preflight.sample_count == 120
            assert len(samples) == 120
            assert samples[0].mission_elapsed_seconds == 30.0

            aggregator = CausalWindowAggregator()
            emitted: list[WindowBuildResult] = []
            for sample in samples:
                emitted.extend(aggregator.ingest(sample))
            ready = [result for result in emitted if result.status == "READY"]
            assert len(ready) == 1
            assert ready[0].window_index == 1
            payload = build_complete_window_payload(
                ready[0],
                ObservedReplayProvenance(
                    dataset_split="validation",
                    source_reference=replay_source_reference(preflight.telemetry_import),
                    telemetry_import_id=telemetry_import_id,
                ),
            )
            adapter = HttpWindowIngestClient(client)
            accepted = adapter.ingest(tractor_id, payload)
            duplicate = adapter.ingest(tractor_id, payload)
            assert accepted.http_status == 201
            assert duplicate.http_status == 200
            assert duplicate.duplicate is True
            forged_payload = {
                **payload,
                "features": {
                    **payload["features"],
                    "engine_rpm__mean": (payload["features"]["engine_rpm__mean"] or 0.0)
                    + 1.0,
                },
            }
            with pytest.raises(WindowIngestHttpError) as forged_error:
                adapter.ingest(tractor_id, forged_payload)
            assert forged_error.value.status_code == 409
            with Session(engine) as session:
                stored_count = session.scalar(
                    select(func.count())
                    .select_from(ScoredWindowRecord)
                    .where(ScoredWindowRecord.tractor_id == UUID(tractor_id))
                )
            assert stored_count == 1

            created_case = client.post(
                f"/v1/tractors/{tractor_id}/inspection-cases",
                json={"assignee": "Equipe de campo", "due_date": "2026-08-30"},
            )
            assert created_case.status_code == 201
            open_case = created_case.json()
            evidence_hash = open_case["evidence_sha256"]
            referenced = open_case["evidence_snapshot"]["referenced_telemetry_imports"]
            assert [item["id"] for item in referenced] == [telemetry_import_id]
            assert client.post(
                f"/v1/tractors/{tractor_id}/inspection-cases",
                json={"assignee": None, "due_date": None},
            ).status_code == 409

            started = client.patch(
                f"/v1/inspection-cases/{open_case['id']}",
                json={"version": 1, "action": "START"},
            )
            assert started.status_code == 200
            assert started.json()["status"] == "IN_PROGRESS"
            assert started.json()["assignee"] == "Equipe de campo"
            assert started.json()["evidence_sha256"] == evidence_hash

            completed = client.patch(
                f"/v1/inspection-cases/{open_case['id']}",
                json={
                    "version": 2,
                    "action": "COMPLETE",
                    "result": "MONITOR",
                    "result_notes": "Revisão preventiva concluída; manter acompanhamento.",
                },
            )
            assert completed.status_code == 200
            assert completed.json()["status"] == "COMPLETED"
            assert completed.json()["version"] == 3
            assert completed.json()["result"] == "MONITOR"
            assert completed.json()["evidence_sha256"] == evidence_hash

        with Session(engine) as session:
            scored = session.scalar(
                select(ScoredWindowRecord).where(
                    ScoredWindowRecord.tractor_id == UUID(tractor_id)
                )
            )
            assert scored is not None
            assert str(scored.telemetry_import_id) == telemetry_import_id
            assert session.scalar(
                select(func.count())
                .select_from(TelemetrySampleRecord)
                .where(TelemetrySampleRecord.import_id == UUID(telemetry_import_id))
            ) == 120
    finally:
        if fleet_id is not None and tractor_id is not None:
            tractor_uuid = UUID(tractor_id)
            with Session(engine) as session, session.begin():
                session.execute(
                    delete(InspectionCaseRecord).where(
                        InspectionCaseRecord.tractor_id == tractor_uuid
                    )
                )
                session.execute(
                    delete(ScoredWindowRecord).where(
                        ScoredWindowRecord.tractor_id == tractor_uuid
                    )
                )
                if telemetry_import_id is not None:
                    import_uuid = UUID(telemetry_import_id)
                    session.execute(
                        delete(TelemetrySampleRecord).where(
                            TelemetrySampleRecord.import_id == import_uuid
                        )
                    )
                    session.execute(
                        delete(TelemetryMissionRecord).where(
                            TelemetryMissionRecord.import_id == import_uuid
                        )
                    )
                    session.execute(
                        delete(TelemetryImportRecord).where(
                            TelemetryImportRecord.id == import_uuid
                        )
                    )
                session.execute(delete(TractorRecord).where(TractorRecord.id == tractor_uuid))
                session.execute(delete(FleetRecord).where(FleetRecord.id == UUID(fleet_id)))
        engine.dispose()
