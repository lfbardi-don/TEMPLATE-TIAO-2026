"""Audit-friendly inspection-case workflow and server-owned evidence snapshots."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Callable
from uuid import uuid4

from tractor_usage.application.auth import Principal
from tractor_usage.application.checklist import agenda_storage, build_inspection_agenda
from tractor_usage.application.contracts import (
    ConflictError,
    CreateInspectionCase,
    InspectionCase,
    InspectionCaseEvent,
    InspectionCaseEventAction,
    InspectionCaseStatus,
    InspectionFinding,
    InvalidInspectionTransitionError,
    NotFoundError,
    Tractor,
    StaleInspectionCaseVersionError,
    UpdateInspectionCase,
)
from tractor_usage.application.interpretation import (
    EXPOSURE_BANDS_VERSION,
    REGIME_LABELS_VERSION,
    exposure_band,
)
from tractor_usage.application.ports import (
    InspectionCaseRepository,
    InspectionRepository,
    TelemetryRepository,
    UsageModel,
)
from tractor_usage.application.use_cases import GetTractorOverviewUseCase
from tractor_usage.application.inspection_workflow import inspection_workflow


SNAPSHOT_SCHEMA_VERSION = "inspection-evidence-v2"
INTERPRETATION_LIMIT = (
    "Operational evidence for preventive review only; it does not diagnose damage, "
    "failure, claim, misuse, fault, or insurance probability."
)
FINDING_NOTES_LIMIT = 1_000
_FINDING_STATUSES_REQUIRING_NOTES = ("ATTENTION", "PROBLEM")


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

    def execute(
        self,
        tractor_id: str,
        request: CreateInspectionCase,
        *,
        authorize_tractor: Callable[[Tractor], None] | None = None,
        actor: Principal | None = None,
    ) -> InspectionCase:
        with self._cases.transaction():
            tractor = self._cases.get_tractor(tractor_id, for_update=True)
            if tractor is None:
                raise NotFoundError("tractor not found")
            if authorize_tractor is not None:
                authorize_tractor(tractor)
            if self._cases.find_active_case(tractor_id) is not None:
                raise ConflictError("tractor already has an active inspection case")
            overview = GetTractorOverviewUseCase(self._inspection, self._model).execute(tractor_id)
            workflow = inspection_workflow(
                self._cases.list_cases(tractor_id), overview.episodes_last_30_days
            )
            if not workflow["can_open_case"]:
                raise ConflictError("no new episodes to inspect since the last completed case")
            new_episode_ids = set(workflow["new_episode_ids"])
            new_episodes = tuple(
                episode for episode in overview.episodes_last_30_days if episode.id in new_episode_ids
            )
            overview = replace(
                overview,
                episodes_last_30_days=new_episodes,
                inspection_agenda=build_inspection_agenda(new_episodes),
            )
            now = datetime.now(timezone.utc)
            periods = self._telemetry.list_periods(tractor_id)
            snapshot = _snapshot(overview, periods, self._model.model_version)
            encoded = _canonical_json(snapshot)
            created = self._cases.create_case(
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
            if actor is not None:
                self._cases.append_event(
                    _event(
                        created, "CREATE", actor, now,
                        prior_status=None,
                        details={"assignee": created.assignee, "due_date": created.due_date},
                    )
                )
            return created


class GetInspectionCasesUseCase:
    def __init__(self, repository: InspectionCaseRepository) -> None:
        self._repository = repository

    def list(self, tractor_id: str | None = None) -> tuple[InspectionCase, ...]:
        if tractor_id is not None and self._repository.get_tractor(tractor_id) is None:
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

    def execute(
        self,
        case_id: str,
        request: UpdateInspectionCase,
        *,
        authorize_case: Callable[[InspectionCase], None] | None = None,
        actor: Principal | None = None,
    ) -> InspectionCase:
        with self._repository.transaction():
            current = self._repository.get_case(case_id, for_update=True)
            if current is None:
                raise NotFoundError("inspection case not found")
            if authorize_case is not None:
                authorize_case(current)
            if request.version != current.version:
                raise StaleInspectionCaseVersionError("inspection case was modified; refresh and retry")
            _validate_action(current, request)
            findings = _validated_findings(current, request)
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
                findings=findings,
                updated_at_utc=now,
                started_at_utc=(now if request.action == "START" else current.started_at_utc),
                completed_at_utc=(now if request.action == "COMPLETE" else current.completed_at_utc),
                cancelled_at_utc=(now if request.action == "CANCEL" else current.cancelled_at_utc),
            )
            updated = self._repository.update_case(next_value)
            if actor is not None:
                self._repository.append_event(
                    _event(
                        updated,
                        request.action,
                        actor,
                        now,
                        prior_status=current.status,
                        details=_action_details(current, updated, request.action),
                    )
                )
            return updated


def _event(
    case: InspectionCase,
    action: InspectionCaseEventAction,
    actor: Principal,
    occurred_at_utc: datetime,
    *,
    prior_status: InspectionCaseStatus | None,
    details: dict[str, object],
) -> InspectionCaseEvent:
    return InspectionCaseEvent(
        id=str(uuid4()),
        case_id=case.id,
        action=action,
        actor_user_id=actor.id,
        actor_worker_id=actor.worker_id,
        actor_role=actor.role,
        occurred_at_utc=occurred_at_utc,
        prior_status=prior_status,
        new_status=case.status,
        case_version=case.version,
        details=details,
    )


def _action_details(
    current: InspectionCase, updated: InspectionCase, action: str
) -> dict[str, object]:
    if action == "UPDATE":
        changes: dict[str, object] = {}
        for field in ("assignee", "due_date"):
            before, after = getattr(current, field), getattr(updated, field)
            if before != after:
                changes[field] = {"from": before, "to": after}
        return {"changes": changes}
    if action in ("COMPLETE", "SAVE_DRAFT"):
        counts = {status: 0 for status in ("OK", "ATTENTION", "PROBLEM", "NOT_CHECKED")}
        for finding in updated.findings or ():
            counts[finding.status] += 1
        return {"result": updated.result, "finding_status_counts": counts}
    return {}


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
    if request.action == "SAVE_DRAFT":
        if (
            current.status != "IN_PROGRESS"
            or current.snapshot_schema_version != "inspection-evidence-v2"
            or request.result is not None
            or request.result_notes is not None
            or request.findings is None
        ):
            raise InvalidInspectionTransitionError("draft findings require an in-progress v2 case")
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


def _validated_findings(
    current: InspectionCase, request: UpdateInspectionCase
) -> tuple[InspectionFinding, ...] | None:
    """Require one finding per snapshotted agenda item when a v2 case completes."""

    if request.action not in ("COMPLETE", "SAVE_DRAFT"):
        if request.findings is not None:
            raise InvalidInspectionTransitionError("findings are only accepted when saving or completing")
        return current.findings
    if current.snapshot_schema_version == "inspection-evidence-v1":
        if request.findings is not None:
            raise InvalidInspectionTransitionError("this case predates the inspection agenda")
        return None
    agenda_ids = _agenda_item_ids(current)
    supplied = request.findings or ()
    by_item = {finding.item_id: finding for finding in supplied}
    if len(by_item) != len(supplied) or not set(by_item).issubset(agenda_ids):
        raise InvalidInspectionTransitionError("findings must name distinct agenda items")
    if request.action == "COMPLETE" and set(by_item) != set(agenda_ids):
        raise InvalidInspectionTransitionError(
            "findings must cover each agenda item exactly once"
        )
    for finding in supplied:
        notes = finding.notes.strip() if finding.notes is not None else ""
        if len(notes) > FINDING_NOTES_LIMIT:
            raise InvalidInspectionTransitionError("finding notes are too long")
        if finding.status in _FINDING_STATUSES_REQUIRING_NOTES and not notes:
            raise InvalidInspectionTransitionError(
                "findings marked ATTENTION or PROBLEM require notes"
            )
    return tuple(
        InspectionFinding(
            item_id=item_id,
            status=by_item[item_id].status,
            notes=(by_item[item_id].notes or "").strip() or None,
        )
        for item_id in agenda_ids
        if item_id in by_item
    )


def _agenda_item_ids(value: InspectionCase) -> tuple[str, ...]:
    agenda = value.evidence_snapshot.get("inspection_agenda")
    items = agenda.get("items") if isinstance(agenda, dict) else None
    if not isinstance(items, list):
        raise ConflictError("inspection case snapshot has no inspection agenda")
    return tuple(str(item["id"]) for item in items)


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
                "exposure_band": exposure_band(score.relative_exposure_score),
                "confidence": score.confidence,
                "observed_hours": score.observed_hours,
                "active_days": score.active_days,
            }
            for score in overview.scores
        },
        "exposure_band_version": EXPOSURE_BANDS_VERSION,
        "previous_30_day_score": overview.previous_30_day_score,
        "trend_30_day": overview.trend_30_day,
        "episodes_last_30_days": [
            {
                "id": episode.id,
                "mission_index": episode.mission_index,
                "started_at_utc": _iso(episode.started_at_utc),
                "ended_at_utc": _iso(episode.ended_at_utc),
                "physical_exposure_seconds": episode.physical_exposure_seconds,
                "conditions": list(episode.conditions),
                "operational_regimes": list(episode.operational_regimes),
            }
            for episode in overview.episodes_last_30_days
        ],
        "regimes": {
            "version": REGIME_LABELS_VERSION,
            "labels": [{"id": label.id, "kind": label.kind} for label in overview.regimes],
        },
        "inspection_agenda": agenda_storage(overview.inspection_agenda),
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
                "source_kind": period.telemetry_import.source_kind,
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
