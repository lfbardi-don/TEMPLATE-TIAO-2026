"""Framework-free values exchanged by the preventive-inspection application."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Mapping


EvidenceRole = Literal["operational_output_only"]
SourceKind = Literal["observed_dataset_replay"]
DatasetSplit = Literal["train", "validation"]
WindowQuality = Literal["complete", "partial_coverage", "boundary_jitter"]
TelemetrySourceFormat = Literal["canonical_csv", "canonical_csv_gz", "fendt314_zip"]
TelemetryTransformVersion = Literal[
    "canonical-pass-through-v1", "fendt314-original-to-1hz-v1"
]
InspectionCaseStatus = Literal["OPEN", "IN_PROGRESS", "COMPLETED", "CANCELLED"]
InspectionCaseAction = Literal["UPDATE", "START", "COMPLETE", "CANCEL"]
InspectionCaseResult = Literal["NO_ACTION", "MONITOR", "MAINTENANCE_RECOMMENDED"]
ReplayProgressStatus = Literal["waiting", "running", "complete", "failed"]
ReplayProgressErrorCode = Literal["DEMO_REPLAY_FAILED"]


class ApplicationError(Exception):
    """Base error intentionally safe to map at the HTTP boundary."""


class NotFoundError(ApplicationError):
    pass


class ConflictError(ApplicationError):
    pass


class StaleInspectionCaseVersionError(ConflictError):
    """An inspection case was changed after the caller's displayed version."""


class InvalidInspectionTransitionError(ConflictError):
    """A requested inspection-case state transition is not allowed."""


class ModelUnavailableError(ApplicationError):
    pass


@dataclass(frozen=True)
class CreateTractor:
    external_id: str
    display_name: str | None


@dataclass(frozen=True)
class CreateFleet:
    name: str
    tractors: tuple[CreateTractor, ...]


@dataclass(frozen=True)
class PhysicalDurations:
    lugging: float
    overload_torque: float
    loaded_high_slip: float
    thermal_under_load: float
    harsh_torque_rise: float
    severe_exposure: float

    def as_model_columns(self) -> dict[str, float]:
        return {
            "lugging__sum": self.lugging,
            "overload_torque__sum": self.overload_torque,
            "loaded_high_slip__sum": self.loaded_high_slip,
            "thermal_under_load__sum": self.thermal_under_load,
            "harsh_torque_rise__sum": self.harsh_torque_rise,
            "severe_exposure__sum": self.severe_exposure,
        }

    def as_storage(self) -> dict[str, float]:
        return {
            "lugging": self.lugging,
            "overload_torque": self.overload_torque,
            "loaded_high_slip": self.loaded_high_slip,
            "thermal_under_load": self.thermal_under_load,
            "harsh_torque_rise": self.harsh_torque_rise,
            "severe_exposure": self.severe_exposure,
        }


@dataclass(frozen=True)
class WindowProvenance:
    source_kind: SourceKind
    dataset_split: DatasetSplit
    source_reference: str

    def as_storage(self) -> dict[str, str | None]:
        return {
            "source_kind": self.source_kind,
            "dataset_split": self.dataset_split,
            "source_reference": self.source_reference,
        }


@dataclass(frozen=True)
class CompleteWindow:
    mission_index: int
    window_index: int
    observed_at_utc: datetime
    sample_count: int
    span_seconds: float
    window_quality: WindowQuality
    features: Mapping[str, float | None]
    physical_durations: PhysicalDurations
    provenance: WindowProvenance
    telemetry_import_id: str


@dataclass(frozen=True)
class Fleet:
    id: str
    name: str
    created_at_utc: datetime


@dataclass(frozen=True)
class Tractor:
    id: str
    fleet_id: str
    external_id: str
    display_name: str | None
    model_name: str
    created_at_utc: datetime


@dataclass(frozen=True)
class FleetRegistration:
    fleet: Fleet
    tractors: tuple[Tractor, ...]


@dataclass(frozen=True)
class ScoredDecision:
    model_version: str
    operational_regime: int
    contextual_rarity_score: float
    contextual_rarity_threshold: float
    physical_eligible: bool
    physical_reasons: tuple[str, ...]
    hybrid_alert: bool
    contextual_reasons: tuple[dict[str, float | str], ...]


@dataclass(frozen=True)
class StoredWindow:
    id: str
    tractor_id: str
    model_version: str
    mission_index: int
    window_index: int
    observed_at_utc: datetime
    sample_count: int
    span_seconds: float
    window_quality: WindowQuality
    features: Mapping[str, float | None]
    physical_durations: PhysicalDurations
    provenance: WindowProvenance
    evidence_role: EvidenceRole
    idempotency_key: str
    fingerprint: str
    decision: ScoredDecision
    created_at_utc: datetime
    telemetry_import_id: str


@dataclass(frozen=True)
class IngestResult:
    window: StoredWindow
    duplicate: bool


@dataclass(frozen=True)
class RecentReplayInference:
    """One committed API decision observed during the current demo replay."""

    mission_index: int
    window_index: int
    model_version: str
    hybrid_alert: bool


@dataclass(frozen=True)
class ReplayProgressSnapshot:
    """Read-only presentation state for one local live-replay invocation."""

    status: ReplayProgressStatus
    tractor_id: str
    telemetry_import_id: str
    dataset_split: Literal["train", "validation"]
    source_doi: str
    source_license: str
    semantic_sha256: str
    total_samples: int
    samples_replayed: int
    ready_windows: int
    created_windows: int
    duplicate_windows: int
    alert_windows: int
    no_data_windows: int
    failures: int
    recent_inferences: tuple[RecentReplayInference, ...]
    error_code: ReplayProgressErrorCode | None


@dataclass(frozen=True)
class LongitudinalSummary:
    horizon_days: int
    status: Literal["OK", "NO_DATA"]
    as_of_utc: datetime
    observed_hours: float
    active_days: int
    calendar_coverage: float
    confidence: Literal["LOW", "MEDIUM", "HIGH"]
    physical_exposure_seconds_per_hour: float | None
    alert_exposure_seconds_per_hour: float | None
    episodes_per_hour: float | None
    episode_count: int
    represented_conditions: tuple[str, ...]
    predominant_regimes: tuple[int, ...]
    component_percentiles: Mapping[str, float]
    relative_exposure_score: float | None


@dataclass(frozen=True)
class InspectionEpisode:
    id: str
    mission_index: int
    started_at_utc: datetime
    ended_at_utc: datetime
    alerted_seconds: float
    physical_exposure_seconds: float
    conditions: tuple[str, ...]
    operational_regimes: tuple[int, ...]
    maximum_contextual_rarity_score: float
    contextual_reasons: tuple[dict[str, float | str], ...]


@dataclass(frozen=True)
class TractorInspectionOverview:
    tractor: Tractor
    fleet: Fleet
    as_of_utc: datetime
    scores: tuple[LongitudinalSummary, ...]
    previous_30_day_score: float | None
    trend_30_day: float | None
    episodes_last_30_days: tuple[InspectionEpisode, ...]
    provenance: tuple[WindowProvenance, ...]


@dataclass(frozen=True)
class InspectionPriority:
    rank: int | None
    tractor: Tractor
    fleet: Fleet
    as_of_utc: datetime
    scores: tuple[LongitudinalSummary, ...]
    previous_30_day_score: float | None
    trend_30_day: float | None
    episodes_last_30_days: tuple[InspectionEpisode, ...]
    provenance: tuple[WindowProvenance, ...]


@dataclass(frozen=True)
class PortfolioInspectionPriorities:
    as_of_utc: datetime
    priorities: tuple[InspectionPriority, ...]


@dataclass(frozen=True)
class FleetInspectionOverview:
    fleet: Fleet
    as_of_utc: datetime
    tractor_count: int
    status_counts: Mapping[str, int]
    priorities: tuple[InspectionPriority, ...]


@dataclass(frozen=True)
class PersistedTelemetrySample:
    """One observed 1 Hz sample before feature engineering or inference."""

    mission_index: int
    mission_origin_position_deciseconds: int
    position_deciseconds: int
    source_row: int
    observed_at_utc: datetime
    values: Mapping[str, float | None]


@dataclass(frozen=True)
class TelemetryMission:
    import_id: str
    mission_index: int
    origin_position_deciseconds: int
    first_position_deciseconds: int
    last_position_deciseconds: int
    first_source_row: int
    last_source_row: int
    started_at_utc: datetime
    ended_at_utc: datetime
    sample_count: int


@dataclass(frozen=True)
class TelemetryImport:
    id: str
    tractor_id: str
    dataset_split: Literal["train", "validation"]
    source_format: TelemetrySourceFormat
    source_file_name: str
    source_member: str | None
    source_size_bytes: int
    source_sha256: str
    semantic_sha256: str
    schema_version: Literal["fendt314-telemetry-v1"]
    transform_version: TelemetryTransformVersion
    epoch_utc: datetime
    sample_count: int
    mission_count: int
    started_at_utc: datetime
    ended_at_utc: datetime
    created_at_utc: datetime


@dataclass(frozen=True)
class TelemetryPeriod:
    tractor: Tractor
    fleet: Fleet
    telemetry_import: TelemetryImport
    missions: tuple[TelemetryMission, ...]


@dataclass(frozen=True)
class TelemetryPeriods:
    tractor: Tractor
    fleet: Fleet
    periods: tuple[TelemetryPeriod, ...]


@dataclass(frozen=True)
class InspectionCase:
    id: str
    tractor_id: str
    status: InspectionCaseStatus
    version: int
    assignee: str | None
    due_date: str | None
    evidence_as_of_utc: datetime
    snapshot_schema_version: Literal["inspection-evidence-v1"]
    evidence_snapshot: Mapping[str, object]
    evidence_sha256: str
    result: InspectionCaseResult | None
    result_notes: str | None
    created_at_utc: datetime
    updated_at_utc: datetime
    started_at_utc: datetime | None
    completed_at_utc: datetime | None
    cancelled_at_utc: datetime | None


@dataclass(frozen=True)
class CreateInspectionCase:
    assignee: str | None
    due_date: str | None


@dataclass(frozen=True)
class UpdateInspectionCase:
    version: int
    action: InspectionCaseAction
    assignee: str | None = None
    due_date: str | None = None
    result: InspectionCaseResult | None = None
    result_notes: str | None = None
    assignee_present: bool = False
    due_date_present: bool = False
