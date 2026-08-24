"""Import and read-use cases for immutable observed telemetry periods."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4

from tractor_usage.application.contracts import (
    ConflictError,
    DatasetSplit,
    NotFoundError,
    TelemetryImport,
    TelemetryMission,
    TelemetryPeriod,
    TelemetryPeriods,
    TelemetryTransformVersion,
)
from tractor_usage.application.ports import TelemetryRepository
from tractor_usage.infrastructure.telemetry_files import EPOCH_UTC, SCHEMA_VERSION, TelemetryFileSource


@dataclass(frozen=True)
class TelemetryImportResult:
    telemetry_import: TelemetryImport
    duplicate: bool


class ImportTelemetryUseCase:
    """Atomically persist exactly the frozen split selected by a local source."""

    def __init__(self, repository: TelemetryRepository) -> None:
        self._repository = repository

    def execute(
        self,
        *,
        source: Path,
        tractor_id: str,
        dataset_split: str,
        batch_size: int = 5_000,
    ) -> TelemetryImportResult:
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        selected_split = _dataset_split(dataset_split)
        file_source = TelemetryFileSource(source, selected_split)
        source_sha256 = file_source.source_sha256
        # A retry of the exact same file can be resolved from its byte identity.
        # New or recompressed content still receives the full semantic scan below.
        with self._repository.transaction():
            tractor = self._repository.get_tractor(tractor_id, for_update=True)
            if tractor is None:
                raise NotFoundError("tractor not found")
            duplicate = self._repository.find_import_by_source(
                tractor_id,
                selected_split,
                source_sha256,
                file_source.transform_version,
            )
            if duplicate is not None:
                return TelemetryImportResult(telemetry_import=duplicate, duplicate=True)

        scan = file_source.scan()
        now = datetime.now(timezone.utc)
        identifier = str(uuid4())
        telemetry_import = TelemetryImport(
            id=identifier,
            tractor_id=tractor_id,
            dataset_split=selected_split,
            source_format=scan.source_format,
            source_file_name=_source_file_name(source),
            source_member=scan.source_member,
            source_size_bytes=file_source.source_size_bytes,
            source_sha256=source_sha256,
            semantic_sha256=scan.semantic_sha256,
            schema_version=_schema_version(SCHEMA_VERSION),
            transform_version=_transform_version(scan.transform_version),
            epoch_utc=EPOCH_UTC,
            sample_count=scan.sample_count,
            mission_count=len(scan.missions),
            started_at_utc=scan.started_at_utc,
            ended_at_utc=scan.ended_at_utc,
            created_at_utc=now,
        )
        missions = tuple(
            TelemetryMission(
                import_id=identifier,
                mission_index=item.mission_index,
                origin_position_deciseconds=item.origin_position_deciseconds,
                first_position_deciseconds=item.first_position_deciseconds,
                last_position_deciseconds=item.last_position_deciseconds,
                first_source_row=item.first_source_row,
                last_source_row=item.last_source_row,
                started_at_utc=item.started_at_utc,
                ended_at_utc=item.ended_at_utc,
                sample_count=item.sample_count,
            )
            for item in scan.missions
        )
        with self._repository.transaction():
            tractor = self._repository.get_tractor(tractor_id, for_update=True)
            if tractor is None:
                raise NotFoundError("tractor not found")
            duplicate = self._repository.find_import_by_source(
                tractor_id, selected_split, source_sha256, scan.transform_version
            )
            if duplicate is not None:
                return TelemetryImportResult(telemetry_import=duplicate, duplicate=True)
            matching_semantic = self._repository.find_import_by_semantic_digest(scan.semantic_sha256)
            if matching_semantic is not None:
                if (
                    matching_semantic.tractor_id == tractor_id
                    and matching_semantic.dataset_split == selected_split
                ):
                    return TelemetryImportResult(telemetry_import=matching_semantic, duplicate=True)
                raise ConflictError("semantic telemetry content already belongs to another tractor or split")
            created = self._repository.create_import(telemetry_import, missions)
            batch = []
            inserted = 0
            for sample in file_source.iter_selected_samples():
                batch.append(sample)
                if len(batch) == batch_size:
                    self._repository.insert_samples(created.id, tuple(batch))
                    inserted += len(batch)
                    batch.clear()
            if batch:
                self._repository.insert_samples(created.id, tuple(batch))
                inserted += len(batch)
            if inserted != created.sample_count:
                raise RuntimeError("source changed while its telemetry import was being persisted")
            return TelemetryImportResult(telemetry_import=created, duplicate=False)


class GetTelemetryPeriodsUseCase:
    def __init__(self, repository: TelemetryRepository) -> None:
        self._repository = repository

    def execute(self, tractor_id: str, *, import_id: str | None = None) -> TelemetryPeriods:
        tractor = self._repository.get_tractor(tractor_id)
        if tractor is None:
            raise NotFoundError("tractor not found")
        fleet = self._repository.get_fleet_for_tractor(tractor_id)
        if fleet is None:
            raise NotFoundError("fleet not found")
        periods = self._repository.list_periods(tractor_id, import_id)
        if import_id is not None and not periods:
            raise NotFoundError("telemetry import not found")
        return TelemetryPeriods(tractor=tractor, fleet=fleet, periods=periods)


def _source_file_name(path: Path) -> str:
    name = path.name
    if not name or len(name) > 255:
        raise ValueError("source file name must contain at most 255 characters")
    return name


def _dataset_split(value: str) -> DatasetSplit:
    if value == "train":
        return "train"
    if value == "validation":
        return "validation"
    raise ValueError("dataset_split must be train or validation")


def _transform_version(value: str) -> TelemetryTransformVersion:
    if value == "canonical-pass-through-v1":
        return "canonical-pass-through-v1"
    if value == "fendt314-original-to-1hz-v1":
        return "fendt314-original-to-1hz-v1"
    raise ValueError("telemetry transform version is unsupported")


def _schema_version(value: str) -> Literal["fendt314-telemetry-v1"]:
    if value != "fendt314-telemetry-v1":
        raise ValueError("telemetry schema version is unsupported")
    return "fendt314-telemetry-v1"
