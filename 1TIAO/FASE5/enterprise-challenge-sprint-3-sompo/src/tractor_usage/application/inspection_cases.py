"""Audit-friendly inspection-case workflow and server-owned evidence snapshots."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
import json
from uuid import uuid4

from tractor_usage.application.contracts import (
    ConflictError,
    CreateInspectionCase,
    InspectionCase,
    InvalidInspectionTransitionError,
    NotFoundError,
    StaleInspectionCaseVersionError,
    UpdateInspectionCase,
)
from tractor_usage.application.ports import (
    InspectionCaseRepository,
    InspectionRepository,
    TelemetryRepository,
    UsageModel,
)
from tractor_usage.application.use_cases import GetTractorOverviewUseCase


SNAPSHOT_SCHEMA_VERSION = "inspection-evidence-v1"
INTERPRETATION_LIMIT = (
    "Operational evidence for preventive review only; it does not diagnose damage, "
    "failure, claim, misuse, fault, or insurance probability."
)


class CreateInspectionCaseUseCase:
    def __init__(
        self,
        case_repository: InspectionCaseRepository,
        inspection_repository: InspectionRepository,
        telemetry_repository: TelemetryRepository,
        model: UsageModel,
    ) -> None:
        self._cases = case_repository
        self._inspection = inspection_repository
        self._telemetry = telemetry_repository
        self._model = model

    def execute(self, tractor_id: str, request: CreateInspectionCase) -> InspectionCase:
        with self._cases.transaction():
            tractor = self._cases.get_tractor(tractor_id, for_update=True)
            if tractor is None:
                raise NotFoundError("tractor not found")
            if self._cases.find_active_case(tractor_id) is not None:
                raise ConflictError("tractor already has an active inspection case")
            overview = GetTractorOverviewUseCase(self._inspection, self._model).execute(tractor_id)
            now = datetime.now(timezone.utc)
            periods = self._telemetry.list_periods(tractor_id)
            snapshot = _snapshot(overview, periods, self._model.model_version)
            encoded = _canonical_json(snapshot)
            return self._cases.create_case(
                InspectionCase(
                    id=str(uuid4()),
                    tractor_id=tractor_id,
                    status="OPEN",
                    version=1,
                    assignee=request.assignee,
                    due_date=request.due_date,
                    evidence_as_of_utc=overview.as_of_utc,
                    snapshot_schema_version=SNAPSHOT_SCHEMA_VERSION,
                    evidence_snapshot=snapshot,
                    evidence_sha256=sha256(encoded).hexdigest(),
                    result=None,
                    result_notes=None,
                    created_at_utc=now,
                    updated_at_utc=now,
                    started_at_utc=None,
                    completed_at_utc=None,
                    cancelled_at_utc=None,
                )
            )


class GetInspectionCasesUseCase:
    def __init__(self, repository: InspectionCaseRepository) -> None:
        self._repository = repository

    def list(self, tractor_id: str) -> tuple[InspectionCase, ...]:
        if self._repository.get_tractor(tractor_id) is None:
            raise NotFoundError("tractor not found")
        return self._repository.list_cases(tractor_id)

    def get(self, case_id: str) -> InspectionCase:
        result = self._repository.get_case(case_id)
        if result is None:
            raise NotFoundError("inspection case not found")
        return result


class UpdateInspectionCaseUseCase:
    def __init__(self, repository: InspectionCaseRepository) -> None:
        self._repository = repository

    def execute(self, case_id: str, request: UpdateInspectionCase) -> InspectionCase:
        with self._repository.transaction():
            current = self._repository.get_case(case_id, for_update=True)
            if current is None:
                raise NotFoundError("inspection case not found")
            if request.version != current.version:
                raise StaleInspectionCaseVersionError("inspection case was modified; refresh and retry")
            _validate_action(current, request)
            now = datetime.now(timezone.utc)
            assignee = request.assignee if request.assignee_present else current.assignee
            due_date = request.due_date if request.due_date_present else current.due_date
            next_value = replace(
                current,
                status=_next_status(current.status, request.action),
                version=current.version + 1,
                assignee=assignee,
                due_date=due_date,
                result=request.result if request.action == "COMPLETE" else None,
                result_notes=request.result_notes if request.action == "COMPLETE" else None,
                updated_at_utc=now,
                started_at_utc=(now if request.action == "START" else current.started_at_utc),
                completed_at_utc=(now if request.action == "COMPLETE" else current.completed_at_utc),
                cancelled_at_utc=(now if request.action == "CANCEL" else current.cancelled_at_utc),
            )
            return self._repository.update_case(next_value)


def _validate_action(current: InspectionCase, request: UpdateInspectionCase) -> None:
    if current.status in ("COMPLETED", "CANCELLED"):
        raise InvalidInspectionTransitionError("inspection case transition is not allowed")
    if request.action == "UPDATE":
        if request.result is not None or request.result_notes is not None:
            raise InvalidInspectionTransitionError("inspection case transition is not allowed")
        return
    if request.action == "START":
        if current.status != "OPEN" or request.result is not None or request.result_notes is not None:
            raise InvalidInspectionTransitionError("inspection case transition is not allowed")
        return
    if request.action == "CANCEL":
        if current.status not in ("OPEN", "IN_PROGRESS") or request.result is not None or request.result_notes is not None:
            raise InvalidInspectionTransitionError("inspection case transition is not allowed")
        return
    if request.action == "COMPLETE":
        if current.status != "IN_PROGRESS" or request.result is None:
            raise InvalidInspectionTransitionError("inspection case transition is not allowed")
        notes = request.result_notes.strip() if request.result_notes is not None else ""
        if not notes or len(notes) > 4_000:
            raise InvalidInspectionTransitionError("inspection case transition is not allowed")
        return
    raise InvalidInspectionTransitionError("inspection case transition is not allowed")


def _next_status(current: str, action: str) -> str:
    if action == "START":
        return "IN_PROGRESS"
    if action == "COMPLETE":
        return "COMPLETED"
    if action == "CANCEL":
        return "CANCELLED"
    return current


def _snapshot(overview, periods, model_version: str) -> dict[str, object]:
    referenced_ids = {
        item.source_reference.split("#", 1)[0].removeprefix("postgresql:telemetry-import:")
        for item in overview.provenance
        if item.source_reference.startswith("postgresql:telemetry-import:")
    }
    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "evidence_as_of_utc": _iso(overview.as_of_utc),
        "model_version": model_version,
        "fleet": {"id": overview.fleet.id, "name": overview.fleet.name},
        "tractor": {
            "id": overview.tractor.id,
            "external_id": overview.tractor.external_id,
            "display_name": overview.tractor.display_name,
            "model_name": overview.tractor.model_name,
        },
        "scores": {
            f"{score.horizon_days}_days": {
                "status": score.status,
                "relative_exposure_score": score.relative_exposure_score,
                "confidence": score.confidence,
                "observed_hours": score.observed_hours,
            }
            for score in overview.scores
        },
        "previous_30_day_score": overview.previous_30_day_score,
        "trend_30_day": overview.trend_30_day,
        "episodes_last_30_days": [
            {
                "id": episode.id,
                "mission_index": episode.mission_index,
                "started_at_utc": _iso(episode.started_at_utc),
                "ended_at_utc": _iso(episode.ended_at_utc),
                "conditions": list(episode.conditions),
                "operational_regimes": list(episode.operational_regimes),
            }
            for episode in overview.episodes_last_30_days
        ],
        "provenance": [
            {
                "source_kind": item.source_kind,
                "dataset_split": item.dataset_split,
                "source_reference": item.source_reference,
            }
            for item in overview.provenance
        ],
        "referenced_telemetry_imports": [
            {
                "id": period.telemetry_import.id,
                "dataset_split": period.telemetry_import.dataset_split,
                "semantic_sha256": period.telemetry_import.semantic_sha256,
                "started_at_utc": _iso(period.telemetry_import.started_at_utc),
                "ended_at_utc": _iso(period.telemetry_import.ended_at_utc),
                "sample_count": period.telemetry_import.sample_count,
                "mission_count": period.telemetry_import.mission_count,
                "replay_status": "ELIGIBLE",
            }
            for period in periods
            if period.telemetry_import.id in referenced_ids
        ],
        "interpretation_limit": INTERPRETATION_LIMIT,
    }


def _canonical_json(value: dict[str, object]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()
