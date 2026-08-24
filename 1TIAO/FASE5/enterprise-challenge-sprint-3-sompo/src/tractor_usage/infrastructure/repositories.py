"""Concrete PostgreSQL persistence without a generic repository layer."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tractor_usage.application.contracts import (
    CompleteWindow,
    ConflictError,
    CreateFleet,
    Fleet,
    FleetRegistration,
    PhysicalDurations,
    NotFoundError,
    ScoredDecision,
    StoredWindow,
    Tractor,
    WindowProvenance,
)
from tractor_usage.infrastructure.models import (
    FleetRecord,
    ScoredWindowRecord,
    TractorRecord,
)
from tractor_usage.infrastructure.postgres_telemetry_replay import (
    PostgresTelemetryReplay,
    replay_source_reference,
)
from tractor_usage.infrastructure.window_mapping import (
    WindowMappingError,
    complete_window_from_build_result,
)
from tractor_usage.streaming.windows import CausalWindowAggregator


class PostgresInspectionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    @contextmanager
    def transaction(self):
        try:
            with self._session.begin():
                yield
        except IntegrityError as error:
            raise ConflictError("duplicate or conflicting persistent identity") from error

    def create_fleet(self, request: CreateFleet) -> FleetRegistration:
        fleet = FleetRecord(name=request.name)
        self._session.add(fleet)
        self._session.flush()
        tractors = [
            TractorRecord(
                fleet_id=fleet.id,
                external_id=tractor.external_id,
                display_name=tractor.display_name,
                model_name="Fendt 314",
            )
            for tractor in request.tractors
        ]
        self._session.add_all(tractors)
        self._session.flush()
        return FleetRegistration(
            fleet=_fleet(fleet), tractors=tuple(_tractor(tractor) for tractor in tractors)
        )

    def get_fleet(self, fleet_id: str) -> Fleet | None:
        record = self._session.get(FleetRecord, _uuid(fleet_id))
        return _fleet(record) if record is not None else None

    def get_tractor(self, tractor_id: str, *, for_update: bool = False) -> Tractor | None:
        statement = select(TractorRecord).where(TractorRecord.id == _uuid(tractor_id))
        if for_update:
            statement = statement.with_for_update()
        record = self._session.scalar(statement)
        return _tractor(record) if record is not None else None

    def list_tractors(self, *, fleet_id: str | None = None) -> tuple[Tractor, ...]:
        statement: Select[tuple[TractorRecord]] = select(TractorRecord).order_by(
            TractorRecord.id
        )
        if fleet_id is not None:
            statement = statement.where(TractorRecord.fleet_id == _uuid(fleet_id))
        return tuple(_tractor(record) for record in self._session.scalars(statement))

    def get_fleet_for_tractor(self, tractor_id: str) -> Fleet | None:
        statement = (
            select(FleetRecord)
            .join(TractorRecord, TractorRecord.fleet_id == FleetRecord.id)
            .where(TractorRecord.id == _uuid(tractor_id))
        )
        record = self._session.scalar(statement)
        return _fleet(record) if record is not None else None

    def find_window_by_idempotency_key(self, key: str) -> StoredWindow | None:
        record = self._session.scalar(
            select(ScoredWindowRecord).where(ScoredWindowRecord.idempotency_key == key)
        )
        return _window(record) if record is not None else None

    def get_latest_window(self, tractor_id: str) -> StoredWindow | None:
        record = self._session.scalar(
            select(ScoredWindowRecord)
            .where(ScoredWindowRecord.tractor_id == _uuid(tractor_id))
            .order_by(
                ScoredWindowRecord.observed_at_utc.desc(),
                ScoredWindowRecord.mission_index.desc(),
                ScoredWindowRecord.window_index.desc(),
                ScoredWindowRecord.id.desc(),
            )
            .limit(1)
        )
        return _window(record) if record is not None else None

    def get_latest_window_in_mission(
        self, tractor_id: str, telemetry_import_id: str, mission_index: int
    ) -> StoredWindow | None:
        record = self._session.scalar(
            select(ScoredWindowRecord)
            .where(
                ScoredWindowRecord.tractor_id == _uuid(tractor_id),
                ScoredWindowRecord.telemetry_import_id == _uuid(telemetry_import_id),
                ScoredWindowRecord.mission_index == mission_index,
            )
            .order_by(
                ScoredWindowRecord.window_index.desc(),
                ScoredWindowRecord.observed_at_utc.desc(),
                ScoredWindowRecord.id.desc(),
            )
            .limit(1)
        )
        return _window(record) if record is not None else None

    def get_mission_provenance(
        self, tractor_id: str, telemetry_import_id: str, mission_index: int
    ) -> WindowProvenance | None:
        record = self._session.scalar(
            select(ScoredWindowRecord)
            .where(
                ScoredWindowRecord.tractor_id == _uuid(tractor_id),
                ScoredWindowRecord.telemetry_import_id == _uuid(telemetry_import_id),
                ScoredWindowRecord.mission_index == mission_index,
            )
            .order_by(ScoredWindowRecord.observed_at_utc)
            .limit(1)
        )
        return _provenance(record) if record is not None else None

    def resolve_observed_window(
        self, tractor_id: str, request: CompleteWindow
    ) -> CompleteWindow:
        """Rebuild and verify a client claim before scoring or persistence."""

        try:
            replay = PostgresTelemetryReplay(
                self._session,
                request.telemetry_import_id,
                mission_index=request.mission_index,
            )
            preflight = replay.preflight()
            telemetry_import = preflight.telemetry_import
            if telemetry_import.tractor_id != tractor_id:
                raise ConflictError("telemetry import does not belong to tractor")
            provenance = WindowProvenance(
                source_kind="observed_dataset_replay",
                dataset_split=telemetry_import.dataset_split,
                source_reference=replay_source_reference(telemetry_import),
            )
            results = []
            aggregator = CausalWindowAggregator()
            for sample in replay.iter_window_samples(
                mission_index=request.mission_index,
                window_index=request.window_index,
            ):
                results.extend(aggregator.ingest(sample))
            results.extend(aggregator.flush())
            ready = [
                result
                for result in results
                if result.status == "READY"
                and result.mission_index == request.mission_index
                and result.window_index == request.window_index
            ]
            if len(ready) != 1:
                raise ConflictError("telemetry import cannot reconstruct the requested ready window")
            authoritative = complete_window_from_build_result(
                ready[0],
                provenance=provenance,
                telemetry_import_id=telemetry_import.id,
            )
        except ConflictError:
            raise
        except (NotFoundError, ValueError, WindowMappingError) as error:
            raise ConflictError("telemetry import cannot verify the requested window") from error

        if authoritative != request:
            raise ConflictError("submitted window differs from persisted observed telemetry")
        return authoritative

    def insert_window(
        self,
        tractor_id: str,
        request: CompleteWindow,
        decision: ScoredDecision,
        *,
        idempotency_key: str,
        fingerprint: str,
    ) -> StoredWindow:
        record = ScoredWindowRecord(
            tractor_id=_uuid(tractor_id),
            telemetry_import_id=_uuid(request.telemetry_import_id),
            model_version=decision.model_version,
            mission_index=request.mission_index,
            window_index=request.window_index,
            observed_at_utc=_utc(request.observed_at_utc),
            sample_count=request.sample_count,
            span_seconds=request.span_seconds,
            window_quality=request.window_quality,
            model_features=dict(request.features),
            physical_durations=request.physical_durations.as_storage(),
            source_kind=request.provenance.source_kind,
            dataset_split=request.provenance.dataset_split,
            source_reference=request.provenance.source_reference,
            evidence_role="operational_output_only",
            operational_regime=decision.operational_regime,
            contextual_rarity_score=decision.contextual_rarity_score,
            contextual_rarity_threshold=decision.contextual_rarity_threshold,
            physical_eligible=decision.physical_eligible,
            physical_reasons=list(decision.physical_reasons),
            hybrid_alert=decision.hybrid_alert,
            contextual_reasons=list(decision.contextual_reasons),
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
        )
        self._session.add(record)
        self._session.flush()
        return _window(record)

    def latest_window_close(
        self,
        *,
        tractor_id: str | None = None,
        fleet_id: str | None = None,
    ) -> datetime | None:
        statement = select(func.max(ScoredWindowRecord.observed_at_utc))
        if tractor_id is not None:
            statement = statement.where(ScoredWindowRecord.tractor_id == _uuid(tractor_id))
        if fleet_id is not None:
            statement = statement.join(
                TractorRecord, TractorRecord.id == ScoredWindowRecord.tractor_id
            ).where(TractorRecord.fleet_id == _uuid(fleet_id))
        observed_at = self._session.scalar(statement)
        return _utc(observed_at) + timedelta(seconds=60) if observed_at is not None else None

    def list_report_windows(
        self, tractor_id: str, *, as_of_utc: datetime
    ) -> tuple[StoredWindow, ...]:
        as_of = _utc(as_of_utc)
        history_start = as_of - timedelta(days=60, seconds=60)
        latest_closed_start = as_of - timedelta(seconds=60)
        base = (
            select(ScoredWindowRecord)
            .where(
                ScoredWindowRecord.tractor_id == _uuid(tractor_id),
                ScoredWindowRecord.observed_at_utc <= latest_closed_start,
            )
        )
        in_range = tuple(
            self._session.scalars(
                base.where(ScoredWindowRecord.observed_at_utc >= history_start).order_by(
                    ScoredWindowRecord.observed_at_utc,
                    ScoredWindowRecord.mission_index,
                    ScoredWindowRecord.window_index,
                    ScoredWindowRecord.id,
                )
            )
        )
        predecessor = self._session.scalar(
            base.where(ScoredWindowRecord.observed_at_utc < history_start)
            .order_by(ScoredWindowRecord.observed_at_utc.desc(), ScoredWindowRecord.id.desc())
            .limit(1)
        )
        records = ((predecessor,) if predecessor is not None else ()) + in_range
        return tuple(_window(record) for record in records)


def _uuid(value: str) -> UUID:
    return UUID(value)


def _utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc)


def _fleet(record: FleetRecord) -> Fleet:
    return Fleet(id=str(record.id), name=record.name, created_at_utc=_utc(record.created_at_utc))


def _tractor(record: TractorRecord) -> Tractor:
    return Tractor(
        id=str(record.id),
        fleet_id=str(record.fleet_id),
        external_id=record.external_id,
        display_name=record.display_name,
        model_name=record.model_name,
        created_at_utc=_utc(record.created_at_utc),
    )


def _provenance(record: ScoredWindowRecord) -> WindowProvenance:
    return WindowProvenance(
        source_kind=record.source_kind,
        dataset_split=record.dataset_split,
        source_reference=record.source_reference,
    )


def _window(record: ScoredWindowRecord) -> StoredWindow:
    durations = record.physical_durations
    return StoredWindow(
        id=str(record.id),
        tractor_id=str(record.tractor_id),
        model_version=record.model_version,
        mission_index=record.mission_index,
        window_index=record.window_index,
        observed_at_utc=_utc(record.observed_at_utc),
        sample_count=record.sample_count,
        span_seconds=record.span_seconds,
        window_quality=record.window_quality,
        features=dict(record.model_features),
        physical_durations=PhysicalDurations(
            lugging=float(durations["lugging"]),
            overload_torque=float(durations["overload_torque"]),
            loaded_high_slip=float(durations["loaded_high_slip"]),
            thermal_under_load=float(durations["thermal_under_load"]),
            harsh_torque_rise=float(durations["harsh_torque_rise"]),
            severe_exposure=float(durations["severe_exposure"]),
        ),
        provenance=_provenance(record),
        evidence_role=record.evidence_role,
        idempotency_key=record.idempotency_key,
        fingerprint=record.fingerprint,
        decision=ScoredDecision(
            model_version=record.model_version,
            operational_regime=record.operational_regime,
            contextual_rarity_score=record.contextual_rarity_score,
            contextual_rarity_threshold=record.contextual_rarity_threshold,
            physical_eligible=record.physical_eligible,
            physical_reasons=tuple(str(reason) for reason in record.physical_reasons),
            hybrid_alert=record.hybrid_alert,
            contextual_reasons=tuple(
                {
                    "feature": str(reason["feature"]),
                    "robust_deviation": float(reason["robust_deviation"]),
                }
                for reason in record.contextual_reasons
            ),
        ),
        created_at_utc=_utc(record.created_at_utc),
        telemetry_import_id=str(record.telemetry_import_id),
    )
