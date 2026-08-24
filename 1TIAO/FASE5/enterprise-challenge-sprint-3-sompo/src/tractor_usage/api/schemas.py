"""HTTP parsing and response projection; Pydantic is confined to this boundary."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, field_validator, model_validator

from tractor_usage.application.contracts import (
    CompleteWindow,
    CreateFleet,
    CreateTractor,
    FleetInspectionOverview,
    FleetRegistration,
    IngestResult,
    CreateInspectionCase,
    InspectionCase,
    InspectionEpisode,
    InspectionPriority,
    LongitudinalSummary,
    PhysicalDurations,
    PortfolioInspectionPriorities,
    ReplayProgressSnapshot,
    TractorInspectionOverview,
    TelemetryPeriods,
    UpdateInspectionCase,
    WindowProvenance,
)
from tractor_usage.features.schema import MODEL_SIGNALS, TRANSIENT_SIGNALS


EXPECTED_FEATURE_KEYS = tuple(
    f"{signal}__{statistic}"
    for signal in MODEL_SIGNALS
    for statistic in (
        (*("mean", "std"), "max") if signal in TRANSIENT_SIGNALS else ("mean", "std")
    )
)


class CreateTractorRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    external_id: Annotated[str, Field(min_length=1, max_length=128)]
    display_name: Annotated[str | None, Field(max_length=120)] = None

    @field_validator("external_id", "display_name")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("value must not be blank")
        return cleaned

    def to_contract(self) -> CreateTractor:
        return CreateTractor(external_id=self.external_id, display_name=self.display_name)


class CreateFleetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=120)]
    tractors: Annotated[list[CreateTractorRequest], Field(min_length=1)]

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("name must not be blank")
        return cleaned

    @model_validator(mode="after")
    def reject_duplicate_external_ids(self) -> "CreateFleetRequest":
        identities = [tractor.external_id for tractor in self.tractors]
        if len(identities) != len(set(identities)):
            raise ValueError("tractors must not repeat external_id")
        return self

    def to_contract(self) -> CreateFleet:
        return CreateFleet(
            name=self.name,
            tractors=tuple(tractor.to_contract() for tractor in self.tractors),
        )


class PhysicalDurationsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lugging: Annotated[FiniteFloat, Field(ge=0, le=60)]
    overload_torque: Annotated[FiniteFloat, Field(ge=0, le=60)]
    loaded_high_slip: Annotated[FiniteFloat, Field(ge=0, le=60)]
    thermal_under_load: Annotated[FiniteFloat, Field(ge=0, le=60)]
    harsh_torque_rise: Annotated[FiniteFloat, Field(ge=0, le=60)]
    severe_exposure: Annotated[FiniteFloat, Field(ge=0, le=60)]

    def to_contract(self) -> PhysicalDurations:
        return PhysicalDurations(**self.model_dump())


class WindowProvenanceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_kind: Literal["observed_dataset_replay"]
    dataset_split: Literal["train", "validation"]
    source_reference: Annotated[str, Field(min_length=1, max_length=512)]

    @field_validator("source_reference")
    @classmethod
    def strip_reference(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("source_reference must not be blank")
        return cleaned

    def to_contract(self) -> WindowProvenance:
        return WindowProvenance(**self.model_dump())


class CompleteWindowRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mission_index: Annotated[int, Field(ge=0)]
    window_index: Annotated[int, Field(ge=0)]
    observed_at_utc: datetime
    sample_count: Annotated[int, Field(ge=55, le=61)]
    span_seconds: FiniteFloat
    window_quality: Literal["complete", "partial_coverage", "boundary_jitter"]
    features: dict[str, FiniteFloat | None]
    physical_durations: PhysicalDurationsRequest
    provenance: WindowProvenanceRequest
    telemetry_import_id: UUID

    @field_validator("observed_at_utc")
    @classmethod
    def require_utc_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("observed_at_utc must include a timezone")
        return value.astimezone(timezone.utc)

    @field_validator("features")
    @classmethod
    def require_exact_feature_keys(
        cls, value: dict[str, FiniteFloat | None]
    ) -> dict[str, FiniteFloat | None]:
        supplied = set(value)
        expected = set(EXPECTED_FEATURE_KEYS)
        if supplied != expected:
            missing = sorted(expected - supplied)
            unexpected = sorted(supplied - expected)
            details = []
            if missing:
                details.append(f"missing: {', '.join(missing)}")
            if unexpected:
                details.append(f"unexpected: {', '.join(unexpected)}")
            raise ValueError("features must exactly match the approved schema (" + "; ".join(details) + ")")
        return value

    @model_validator(mode="after")
    def require_complete_window_shape(self) -> "CompleteWindowRequest":
        quality_rules = {
            "partial_coverage": (range(55, 60), 54.0),
            "complete": (range(60, 61), 54.0),
            "boundary_jitter": (range(61, 62), 59.0),
        }
        expected_counts, minimum_span = quality_rules[self.window_quality]
        if self.sample_count not in expected_counts or not (
            minimum_span <= self.span_seconds <= 60.000001
        ):
            raise ValueError("sample_count, span_seconds and window_quality do not form a complete window")
        return self

    def to_contract(self) -> CompleteWindow:
        return CompleteWindow(
            mission_index=self.mission_index,
            window_index=self.window_index,
            observed_at_utc=self.observed_at_utc,
            sample_count=self.sample_count,
            span_seconds=self.span_seconds,
            window_quality=self.window_quality,
            features=dict(self.features),
            physical_durations=self.physical_durations.to_contract(),
            provenance=self.provenance.to_contract(),
            telemetry_import_id=str(self.telemetry_import_id),
        )


class CreateInspectionCaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assignee: Annotated[str | None, Field(max_length=120)] = None
    due_date: date | None = None

    @field_validator("assignee")
    @classmethod
    def strip_assignee(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("assignee must not be blank")
        return cleaned

    def to_contract(self) -> CreateInspectionCase:
        return CreateInspectionCase(
            assignee=self.assignee,
            due_date=self.due_date.isoformat() if self.due_date is not None else None,
        )


class UpdateInspectionCaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Annotated[int, Field(ge=1)]
    action: Literal["UPDATE", "START", "COMPLETE", "CANCEL"]
    assignee: Annotated[str | None, Field(max_length=120)] = None
    due_date: date | None = None
    result: Literal["NO_ACTION", "MONITOR", "MAINTENANCE_RECOMMENDED"] | None = None
    result_notes: Annotated[str | None, Field(max_length=4_000)] = None

    @field_validator("assignee")
    @classmethod
    def strip_updated_assignee(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("assignee must not be blank")
        return cleaned

    def to_contract(self) -> UpdateInspectionCase:
        return UpdateInspectionCase(
            version=self.version,
            action=self.action,
            assignee=self.assignee,
            due_date=self.due_date.isoformat() if self.due_date is not None else None,
            result=self.result,
            result_notes=self.result_notes,
            assignee_present="assignee" in self.model_fields_set,
            due_date_present="due_date" in self.model_fields_set,
        )


def fleet_registration_response(value: FleetRegistration) -> dict[str, object]:
    return {
        "evidence_role": "operational_output_only",
        "fleet": _fleet(value.fleet),
        "tractors": [_tractor(tractor) for tractor in value.tractors],
    }


def ingest_response(value: IngestResult) -> dict[str, object]:
    window = value.window
    return {
        "evidence_role": window.evidence_role,
        "duplicate": value.duplicate,
        "window": {
            "id": window.id,
            "tractor_id": window.tractor_id,
            "model_version": window.model_version,
            "mission_index": window.mission_index,
            "window_index": window.window_index,
            "observed_at_utc": _iso(window.observed_at_utc),
            "sample_count": window.sample_count,
            "span_seconds": window.span_seconds,
            "window_quality": window.window_quality,
            "idempotency_key": window.idempotency_key,
            "provenance": _provenance(window.provenance),
            "telemetry_import_id": window.telemetry_import_id,
            "decision": _decision(window.decision),
        },
    }


def portfolio_response(value: PortfolioInspectionPriorities) -> dict[str, object]:
    return {
        "evidence_role": "operational_output_only",
        "as_of_utc": _iso(value.as_of_utc),
        "priorities": [_priority(item) for item in value.priorities],
    }


def fleet_overview_response(value: FleetInspectionOverview) -> dict[str, object]:
    return {
        "evidence_role": "operational_output_only",
        "fleet": _fleet(value.fleet),
        "as_of_utc": _iso(value.as_of_utc),
        "totals": {"tractors": value.tractor_count},
        "status_counts": dict(value.status_counts),
        "priorities": [_priority(item) for item in value.priorities],
    }


def tractor_overview_response(value: TractorInspectionOverview) -> dict[str, object]:
    current = _score_by_horizon(value.scores, 30)
    return {
        "evidence_role": "operational_output_only",
        "fleet": _fleet(value.fleet),
        "tractor": _tractor(value.tractor),
        "as_of_utc": _iso(value.as_of_utc),
        "scores": _scores(value.scores),
        "previous_30_day_score": value.previous_30_day_score,
        "trend_30_day": value.trend_30_day,
        "confidence": current.confidence,
        "observed_hours": current.observed_hours,
        "episodes_last_30_days": [_episode(episode) for episode in value.episodes_last_30_days],
        "provenance": [_provenance(item) for item in value.provenance],
    }


def telemetry_periods_response(value: TelemetryPeriods) -> dict[str, object]:
    return {
        "evidence_role": "operational_output_only",
        "tractor": _tractor(value.tractor),
        "fleet": _fleet(value.fleet),
        "imports": [_telemetry_import_period(period) for period in value.periods],
    }


def inspection_case_response(value: InspectionCase) -> dict[str, object]:
    return {
        "evidence_role": "operational_output_only",
        "id": value.id,
        "tractor_id": value.tractor_id,
        "status": value.status,
        "version": value.version,
        "assignee": value.assignee,
        "due_date": value.due_date,
        "evidence_as_of_utc": _iso(value.evidence_as_of_utc),
        "snapshot_schema_version": value.snapshot_schema_version,
        "evidence_snapshot": dict(value.evidence_snapshot),
        "evidence_sha256": value.evidence_sha256,
        "result": value.result,
        "result_notes": value.result_notes,
        "created_at_utc": _iso(value.created_at_utc),
        "updated_at_utc": _iso(value.updated_at_utc),
        "started_at_utc": _optional_iso(value.started_at_utc),
        "completed_at_utc": _optional_iso(value.completed_at_utc),
        "cancelled_at_utc": _optional_iso(value.cancelled_at_utc),
    }


def inspection_cases_response(value: tuple[InspectionCase, ...]) -> dict[str, object]:
    return {
        "evidence_role": "operational_output_only",
        "cases": [inspection_case_response(case) for case in value],
    }


def replay_progress_response(value: ReplayProgressSnapshot) -> dict[str, object]:
    """Project the injected, invocation-local replay tracker at the HTTP edge."""

    return {
        "evidence_role": "operational_output_only",
        "status": value.status,
        "tractor_id": value.tractor_id,
        "telemetry_import_id": value.telemetry_import_id,
        "dataset_split": value.dataset_split,
        "source_doi": value.source_doi,
        "source_license": value.source_license,
        "semantic_sha256": value.semantic_sha256,
        "total_samples": value.total_samples,
        "samples_replayed": value.samples_replayed,
        "ready_windows": value.ready_windows,
        "created_windows": value.created_windows,
        "duplicate_windows": value.duplicate_windows,
        "alert_windows": value.alert_windows,
        "no_data_windows": value.no_data_windows,
        "failures": value.failures,
        "recent_inferences": [
            {
                "mission_index": inference.mission_index,
                "window_index": inference.window_index,
                "model_version": inference.model_version,
                "hybrid_alert": inference.hybrid_alert,
            }
            for inference in value.recent_inferences
        ],
        "error_code": value.error_code,
    }


def _priority(value: InspectionPriority) -> dict[str, object]:
    current = _score_by_horizon(value.scores, 30)
    return {
        "rank": value.rank,
        "fleet": _fleet(value.fleet),
        "tractor": _tractor(value.tractor),
        "as_of_utc": _iso(value.as_of_utc),
        "scores": _scores(value.scores),
        "previous_30_day_score": value.previous_30_day_score,
        "trend_30_day": value.trend_30_day,
        "confidence": current.confidence,
        "observed_hours": current.observed_hours,
        "episode_count": len(value.episodes_last_30_days),
        "predominant_conditions": list(current.represented_conditions),
        "episodes_last_30_days": [_episode(episode) for episode in value.episodes_last_30_days],
        "provenance": [_provenance(item) for item in value.provenance],
    }


def _fleet(value) -> dict[str, object]:
    return {"id": value.id, "name": value.name, "created_at_utc": _iso(value.created_at_utc)}


def _tractor(value) -> dict[str, object]:
    return {
        "id": value.id,
        "fleet_id": value.fleet_id,
        "external_id": value.external_id,
        "display_name": value.display_name,
        "model_name": value.model_name,
        "created_at_utc": _iso(value.created_at_utc),
    }


def _decision(value) -> dict[str, object]:
    return {
        "operational_regime": value.operational_regime,
        "contextual_rarity_score": value.contextual_rarity_score,
        "contextual_rarity_threshold": value.contextual_rarity_threshold,
        "physical_eligible": value.physical_eligible,
        "physical_reasons": list(value.physical_reasons),
        "hybrid_alert": value.hybrid_alert,
        "contextual_reasons": [dict(reason) for reason in value.contextual_reasons],
    }


def _scores(values: tuple[LongitudinalSummary, ...]) -> dict[str, object]:
    return {f"{value.horizon_days}_days": _score(value) for value in values}


def _score(value: LongitudinalSummary) -> dict[str, object]:
    return {
        "status": value.status,
        "as_of_utc": _iso(value.as_of_utc),
        "observed_hours": value.observed_hours,
        "active_days": value.active_days,
        "calendar_coverage": value.calendar_coverage,
        "confidence": value.confidence,
        "physical_exposure_seconds_per_hour": value.physical_exposure_seconds_per_hour,
        "alert_exposure_seconds_per_hour": value.alert_exposure_seconds_per_hour,
        "episodes_per_hour": value.episodes_per_hour,
        "episode_count": value.episode_count,
        "represented_conditions": list(value.represented_conditions),
        "predominant_regimes": list(value.predominant_regimes),
        "component_percentiles": dict(value.component_percentiles),
        "relative_exposure_score": value.relative_exposure_score,
    }


def _episode(value: InspectionEpisode) -> dict[str, object]:
    return {
        "id": value.id,
        "mission_index": value.mission_index,
        "started_at_utc": _iso(value.started_at_utc),
        "ended_at_utc": _iso(value.ended_at_utc),
        "alerted_seconds": value.alerted_seconds,
        "physical_exposure_seconds": value.physical_exposure_seconds,
        "conditions": list(value.conditions),
        "operational_regimes": list(value.operational_regimes),
        "maximum_contextual_rarity_score": value.maximum_contextual_rarity_score,
        "contextual_reasons": [dict(reason) for reason in value.contextual_reasons],
    }


def _provenance(value: WindowProvenance) -> dict[str, object]:
    return {
        "source_kind": value.source_kind,
        "dataset_split": value.dataset_split,
        "source_reference": value.source_reference,
    }


def _telemetry_import_period(value: TelemetryPeriod) -> dict[str, object]:
    telemetry_import = value.telemetry_import
    return {
        "id": telemetry_import.id,
        "dataset_split": telemetry_import.dataset_split,
        "source_format": telemetry_import.source_format,
        "source_file_name": telemetry_import.source_file_name,
        "source_member": telemetry_import.source_member,
        "semantic_sha256": telemetry_import.semantic_sha256,
        "source_sha256": telemetry_import.source_sha256,
        "transform_version": telemetry_import.transform_version,
        "started_at_utc": _iso(telemetry_import.started_at_utc),
        "ended_at_utc": _iso(telemetry_import.ended_at_utc),
        "sample_count": telemetry_import.sample_count,
        "mission_count": telemetry_import.mission_count,
        "missions": [
            {
                "mission_index": mission.mission_index,
                "started_at_utc": _iso(mission.started_at_utc),
                "ended_at_utc": _iso(mission.ended_at_utc),
                "sample_count": mission.sample_count,
                "observed_duration_seconds": (
                    mission.last_position_deciseconds - mission.first_position_deciseconds
                ) / 10.0,
                "replay_status": "ELIGIBLE",
            }
            for mission in value.missions
        ],
    }


def _score_by_horizon(values: tuple[LongitudinalSummary, ...], horizon: int) -> LongitudinalSummary:
    return next(value for value in values if value.horizon_days == horizon)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _optional_iso(value: datetime | None) -> str | None:
    return _iso(value) if value is not None else None
