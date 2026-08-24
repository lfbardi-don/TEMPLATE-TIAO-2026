"""Narrow ports required by the use cases."""

from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import datetime
from typing import Protocol

from tractor_usage.application.contracts import (
    CompleteWindow,
    CreateFleet,
    Fleet,
    FleetRegistration,
    LongitudinalSummary,
    ScoredDecision,
    StoredWindow,
    Tractor,
    TelemetryImport,
    TelemetryMission,
    TelemetryPeriod,
    PersistedTelemetrySample,
    InspectionCase,
    WindowProvenance,
    ReplayProgressSnapshot,
)


class ReplayProgressReader(Protocol):
    """Read-only presentation seam for an invocation-local demo replay."""

    def snapshot(self) -> ReplayProgressSnapshot: ...


class InspectionRepository(Protocol):
    def transaction(self) -> AbstractContextManager[None]: ...

    def create_fleet(self, request: CreateFleet) -> FleetRegistration: ...

    def get_fleet(self, fleet_id: str) -> Fleet | None: ...

    def get_tractor(self, tractor_id: str, *, for_update: bool = False) -> Tractor | None: ...

    def list_tractors(self, *, fleet_id: str | None = None) -> tuple[Tractor, ...]: ...

    def get_fleet_for_tractor(self, tractor_id: str) -> Fleet | None: ...

    def find_window_by_idempotency_key(self, key: str) -> StoredWindow | None: ...

    def get_latest_window(self, tractor_id: str) -> StoredWindow | None: ...

    def get_latest_window_in_mission(
        self, tractor_id: str, telemetry_import_id: str, mission_index: int
    ) -> StoredWindow | None: ...

    def get_mission_provenance(
        self, tractor_id: str, telemetry_import_id: str, mission_index: int
    ) -> WindowProvenance | None: ...

    def insert_window(
        self,
        tractor_id: str,
        request: CompleteWindow,
        decision: ScoredDecision,
        *,
        idempotency_key: str,
        fingerprint: str,
    ) -> StoredWindow: ...

    def latest_window_close(
        self,
        *,
        tractor_id: str | None = None,
        fleet_id: str | None = None,
    ) -> datetime | None: ...

    def list_report_windows(
        self, tractor_id: str, *, as_of_utc: datetime
    ) -> tuple[StoredWindow, ...]: ...

    def resolve_observed_window(
        self, tractor_id: str, request: CompleteWindow
    ) -> CompleteWindow: ...


class TelemetryRepository(Protocol):
    def transaction(self) -> AbstractContextManager[None]: ...

    def get_tractor(self, tractor_id: str, *, for_update: bool = False) -> Tractor | None: ...

    def get_fleet_for_tractor(self, tractor_id: str) -> Fleet | None: ...

    def find_import_by_source(
        self, tractor_id: str, dataset_split: str, source_sha256: str, transform_version: str
    ) -> TelemetryImport | None: ...

    def find_import_by_semantic_digest(self, semantic_sha256: str) -> TelemetryImport | None: ...

    def create_import(
        self, telemetry_import: TelemetryImport, missions: tuple[TelemetryMission, ...]
    ) -> TelemetryImport: ...

    def insert_samples(
        self, import_id: str, samples: tuple[PersistedTelemetrySample, ...]
    ) -> None: ...

    def list_periods(self, tractor_id: str, import_id: str | None = None) -> tuple[TelemetryPeriod, ...]: ...


class InspectionCaseRepository(Protocol):
    def transaction(self) -> AbstractContextManager[None]: ...

    def get_tractor(self, tractor_id: str, *, for_update: bool = False) -> Tractor | None: ...

    def get_fleet_for_tractor(self, tractor_id: str) -> Fleet | None: ...

    def find_active_case(self, tractor_id: str) -> InspectionCase | None: ...

    def create_case(self, value: InspectionCase) -> InspectionCase: ...

    def get_case(self, case_id: str, *, for_update: bool = False) -> InspectionCase | None: ...

    def list_cases(self, tractor_id: str) -> tuple[InspectionCase, ...]: ...

    def update_case(self, value: InspectionCase) -> InspectionCase: ...


class UsageModel(Protocol):
    @property
    def model_version(self) -> str: ...

    def score(self, tractor_id: str, window: CompleteWindow) -> ScoredDecision: ...

    def aggregate(
        self, windows: tuple[StoredWindow, ...], *, as_of_utc: datetime
    ) -> tuple[LongitudinalSummary, ...]: ...
