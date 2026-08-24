"""PostgreSQL adapter for observed telemetry imports and period queries."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tractor_usage.application.contracts import (
    ConflictError,
    DatasetSplit,
    Fleet,
    PersistedTelemetrySample,
    TelemetryImport,
    TelemetryMission,
    TelemetryPeriod,
    TelemetrySourceFormat,
    TelemetryTransformVersion,
    Tractor,
)
from tractor_usage.infrastructure.models import (
    FleetRecord,
    TelemetryImportRecord,
    TelemetryMissionRecord,
    TelemetrySampleRecord,
    TractorRecord,
)


class PostgresTelemetryRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    @contextmanager
    def transaction(self):
        try:
            with self._session.begin():
                yield
        except IntegrityError as error:
            raise ConflictError("duplicate or conflicting telemetry persistence") from error

    def get_tractor(self, tractor_id: str, *, for_update: bool = False) -> Tractor | None:
        statement = select(TractorRecord).where(TractorRecord.id == _uuid(tractor_id))
        if for_update:
            statement = statement.with_for_update()
        record = self._session.scalar(statement)
        return _tractor(record) if record is not None else None

    def get_fleet_for_tractor(self, tractor_id: str) -> Fleet | None:
        record = self._session.scalar(
            select(FleetRecord)
            .join(TractorRecord, TractorRecord.fleet_id == FleetRecord.id)
            .where(TractorRecord.id == _uuid(tractor_id))
        )
        return _fleet(record) if record is not None else None

    def find_import_by_source(
        self, tractor_id: str, dataset_split: str, source_sha256: str, transform_version: str
    ) -> TelemetryImport | None:
        record = self._session.scalar(
            select(TelemetryImportRecord).where(
                TelemetryImportRecord.tractor_id == _uuid(tractor_id),
                TelemetryImportRecord.dataset_split == dataset_split,
                TelemetryImportRecord.source_sha256 == source_sha256,
                TelemetryImportRecord.transform_version == transform_version,
            )
        )
        return _import(record) if record is not None else None

    def find_import_by_semantic_digest(self, semantic_sha256: str) -> TelemetryImport | None:
        record = self._session.scalar(
            select(TelemetryImportRecord).where(
                TelemetryImportRecord.semantic_sha256 == semantic_sha256
            )
        )
        return _import(record) if record is not None else None

    def create_import(
        self, telemetry_import: TelemetryImport, missions: tuple[TelemetryMission, ...]
    ) -> TelemetryImport:
        record = TelemetryImportRecord(
            id=_uuid(telemetry_import.id),
            tractor_id=_uuid(telemetry_import.tractor_id),
            dataset_split=telemetry_import.dataset_split,
            source_format=telemetry_import.source_format,
            source_file_name=telemetry_import.source_file_name,
            source_member=telemetry_import.source_member,
            source_size_bytes=telemetry_import.source_size_bytes,
            source_sha256=telemetry_import.source_sha256,
            semantic_sha256=telemetry_import.semantic_sha256,
            schema_version=telemetry_import.schema_version,
            transform_version=telemetry_import.transform_version,
            epoch_utc=_utc(telemetry_import.epoch_utc),
            sample_count=telemetry_import.sample_count,
            mission_count=telemetry_import.mission_count,
            started_at_utc=_utc(telemetry_import.started_at_utc),
            ended_at_utc=_utc(telemetry_import.ended_at_utc),
            created_at_utc=_utc(telemetry_import.created_at_utc),
        )
        self._session.add(record)
        self._session.flush()
        self._session.add_all(
            TelemetryMissionRecord(
                import_id=record.id,
                mission_index=mission.mission_index,
                origin_position_deciseconds=mission.origin_position_deciseconds,
                first_position_deciseconds=mission.first_position_deciseconds,
                last_position_deciseconds=mission.last_position_deciseconds,
                first_source_row=mission.first_source_row,
                last_source_row=mission.last_source_row,
                started_at_utc=_utc(mission.started_at_utc),
                ended_at_utc=_utc(mission.ended_at_utc),
                sample_count=mission.sample_count,
            )
            for mission in missions
        )
        self._session.flush()
        return _import(record)

    def insert_samples(
        self, import_id: str, samples: tuple[PersistedTelemetrySample, ...]
    ) -> None:
        identifier = _uuid(import_id)
        self._session.add_all(
            TelemetrySampleRecord(
                import_id=identifier,
                mission_index=sample.mission_index,
                position_deciseconds=sample.position_deciseconds,
                source_row=sample.source_row,
                observed_at_utc=_utc(sample.observed_at_utc),
                **dict(sample.values),
            )
            for sample in samples
        )
        self._session.flush()

    def list_periods(self, tractor_id: str, import_id: str | None = None) -> tuple[TelemetryPeriod, ...]:
        statement = select(TelemetryImportRecord).where(
            TelemetryImportRecord.tractor_id == _uuid(tractor_id)
        )
        if import_id is not None:
            statement = statement.where(TelemetryImportRecord.id == _uuid(import_id))
        imports = tuple(
            self._session.scalars(statement.order_by(TelemetryImportRecord.started_at_utc, TelemetryImportRecord.id))
        )
        tractor = self.get_tractor(tractor_id)
        fleet = self.get_fleet_for_tractor(tractor_id)
        if tractor is None or fleet is None:
            return ()
        periods: list[TelemetryPeriod] = []
        for record in imports:
            missions = tuple(
                _mission(mission)
                for mission in self._session.scalars(
                    select(TelemetryMissionRecord)
                    .where(TelemetryMissionRecord.import_id == record.id)
                    .order_by(TelemetryMissionRecord.mission_index)
                )
            )
            periods.append(
                TelemetryPeriod(
                    tractor=tractor,
                    fleet=fleet,
                    telemetry_import=_import(record),
                    missions=missions,
                )
            )
        return tuple(periods)


def _uuid(value: str) -> UUID:
    return UUID(value)


def _utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc)


def _tractor(record: TractorRecord) -> Tractor:
    return Tractor(
        id=str(record.id),
        fleet_id=str(record.fleet_id),
        external_id=record.external_id,
        display_name=record.display_name,
        model_name=record.model_name,
        created_at_utc=_utc(record.created_at_utc),
    )


def _fleet(record: FleetRecord) -> Fleet:
    return Fleet(id=str(record.id), name=record.name, created_at_utc=_utc(record.created_at_utc))


def _import(record: TelemetryImportRecord) -> TelemetryImport:
    return TelemetryImport(
        id=str(record.id),
        tractor_id=str(record.tractor_id),
        dataset_split=_dataset_split(record.dataset_split),
        source_format=_source_format(record.source_format),
        source_file_name=record.source_file_name,
        source_member=record.source_member,
        source_size_bytes=record.source_size_bytes,
        source_sha256=record.source_sha256,
        semantic_sha256=record.semantic_sha256,
        schema_version=_schema_version(record.schema_version),
        transform_version=_transform_version(record.transform_version),
        epoch_utc=_utc(record.epoch_utc),
        sample_count=record.sample_count,
        mission_count=record.mission_count,
        started_at_utc=_utc(record.started_at_utc),
        ended_at_utc=_utc(record.ended_at_utc),
        created_at_utc=_utc(record.created_at_utc),
    )


def _dataset_split(value: str) -> DatasetSplit:
    if value == "train":
        return "train"
    if value == "validation":
        return "validation"
    raise ValueError("persisted telemetry import has an unsupported dataset split")


def _source_format(value: str) -> TelemetrySourceFormat:
    if value == "canonical_csv":
        return "canonical_csv"
    if value == "canonical_csv_gz":
        return "canonical_csv_gz"
    if value == "fendt314_zip":
        return "fendt314_zip"
    raise ValueError("persisted telemetry import has an unsupported source format")


def _schema_version(value: str) -> Literal["fendt314-telemetry-v1"]:
    if value != "fendt314-telemetry-v1":
        raise ValueError("persisted telemetry import has an unsupported schema version")
    return "fendt314-telemetry-v1"


def _transform_version(value: str) -> TelemetryTransformVersion:
    if value == "canonical-pass-through-v1":
        return "canonical-pass-through-v1"
    if value == "fendt314-original-to-1hz-v1":
        return "fendt314-original-to-1hz-v1"
    raise ValueError("persisted telemetry import has an unsupported transform version")


def _mission(record: TelemetryMissionRecord) -> TelemetryMission:
    return TelemetryMission(
        import_id=str(record.import_id),
        mission_index=record.mission_index,
        origin_position_deciseconds=record.origin_position_deciseconds,
        first_position_deciseconds=record.first_position_deciseconds,
        last_position_deciseconds=record.last_position_deciseconds,
        first_source_row=record.first_source_row,
        last_source_row=record.last_source_row,
        started_at_utc=_utc(record.started_at_utc),
        ended_at_utc=_utc(record.ended_at_utc),
        sample_count=record.sample_count,
    )
