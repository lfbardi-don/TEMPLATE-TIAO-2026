"""PostgreSQL persistence for immutable-evidence inspection cases."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tractor_usage.application.contracts import (
    ConflictError,
    InspectionCase,
    InspectionCaseEvent,
    InspectionCaseEventAction,
    InspectionCaseResult,
    InspectionCaseStatus,
    InspectionFinding,
    InspectionFindingStatus,
    InspectionSnapshotSchemaVersion,
    Tractor,
)
from tractor_usage.infrastructure.models import (
    InspectionCaseEventRecord,
    InspectionCaseRecord,
    TractorRecord,
)


class PostgresInspectionCaseRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    @contextmanager
    def transaction(self):
        try:
            with self._session.begin():
                yield
        except IntegrityError as error:
            raise ConflictError("duplicate or conflicting inspection case persistence") from error

    def get_tractor(self, tractor_id: str, *, for_update: bool = False) -> Tractor | None:
        statement = select(TractorRecord).where(TractorRecord.id == _uuid(tractor_id))
        if for_update:
            statement = statement.with_for_update()
        record = self._session.scalar(statement)
        return _tractor(record) if record is not None else None

    def find_active_case(self, tractor_id: str) -> InspectionCase | None:
        record = self._session.scalar(
            select(InspectionCaseRecord)
            .where(
                InspectionCaseRecord.tractor_id == _uuid(tractor_id),
                InspectionCaseRecord.status.in_(("OPEN", "IN_PROGRESS")),
            )
            .order_by(InspectionCaseRecord.created_at_utc.desc(), InspectionCaseRecord.id.desc())
            .limit(1)
        )
        return _case(record) if record is not None else None

    def create_case(self, value: InspectionCase) -> InspectionCase:
        record = InspectionCaseRecord(
            id=_uuid(value.id),
            tractor_id=_uuid(value.tractor_id),
            status=value.status,
            version=value.version,
            assignee=value.assignee,
            due_date=_date(value.due_date),
            evidence_as_of_utc=_utc(value.evidence_as_of_utc),
            snapshot_schema_version=value.snapshot_schema_version,
            evidence_snapshot=dict(value.evidence_snapshot),
            evidence_sha256=value.evidence_sha256,
            result=value.result,
            result_notes=value.result_notes,
            findings=_findings_storage(value.findings),
            created_at_utc=_utc(value.created_at_utc),
            updated_at_utc=_utc(value.updated_at_utc),
            started_at_utc=_optional_utc(value.started_at_utc),
            completed_at_utc=_optional_utc(value.completed_at_utc),
            cancelled_at_utc=_optional_utc(value.cancelled_at_utc),
        )
        self._session.add(record)
        self._session.flush()
        return _case(record)

    def get_case(self, case_id: str, *, for_update: bool = False) -> InspectionCase | None:
        statement = select(InspectionCaseRecord).where(InspectionCaseRecord.id == _uuid(case_id))
        if for_update:
            statement = statement.with_for_update()
        record = self._session.scalar(statement)
        return _case(record) if record is not None else None

    def list_cases(self, tractor_id: str | None = None) -> tuple[InspectionCase, ...]:
        statement = select(InspectionCaseRecord)
        if tractor_id is not None:
            statement = statement.where(InspectionCaseRecord.tractor_id == _uuid(tractor_id))
        return tuple(
            _case(record)
            for record in self._session.scalars(
                statement.order_by(InspectionCaseRecord.created_at_utc.desc(), InspectionCaseRecord.id.desc())
            )
        )

    def update_case(self, value: InspectionCase) -> InspectionCase:
        record = self._session.get(InspectionCaseRecord, _uuid(value.id))
        if record is None:
            raise ConflictError("inspection case disappeared during update")
        record.status = value.status
        record.version = value.version
        record.assignee = value.assignee
        record.due_date = _date(value.due_date)
        record.result = value.result
        record.result_notes = value.result_notes
        record.findings = _findings_storage(value.findings)
        record.updated_at_utc = _utc(value.updated_at_utc)
        record.started_at_utc = _optional_utc(value.started_at_utc)
        record.completed_at_utc = _optional_utc(value.completed_at_utc)
        record.cancelled_at_utc = _optional_utc(value.cancelled_at_utc)
        # Snapshot and evidence hash are intentionally never assigned here.
        self._session.flush()
        return _case(record)

    def append_event(self, value: InspectionCaseEvent) -> None:
        self._session.add(
            InspectionCaseEventRecord(
                id=_uuid(value.id),
                case_id=_uuid(value.case_id),
                action=value.action,
                actor_user_id=_uuid(value.actor_user_id),
                actor_worker_id=value.actor_worker_id,
                actor_role=value.actor_role,
                occurred_at_utc=_utc(value.occurred_at_utc),
                prior_status=value.prior_status,
                new_status=value.new_status,
                case_version=value.case_version,
                details=dict(value.details),
            )
        )
        self._session.flush()

    def list_events(self, case_id: str) -> tuple[InspectionCaseEvent, ...]:
        return tuple(
            _case_event(record)
            for record in self._session.scalars(
                select(InspectionCaseEventRecord)
                .where(InspectionCaseEventRecord.case_id == _uuid(case_id))
                .order_by(InspectionCaseEventRecord.case_version, InspectionCaseEventRecord.id)
            )
        )


def _uuid(value: str) -> UUID:
    return UUID(value)


def _utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc)


def _optional_utc(value: datetime | None) -> datetime | None:
    return _utc(value) if value is not None else None


def _date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value is not None else None


def _tractor(record: TractorRecord) -> Tractor:
    return Tractor(str(record.id), str(record.fleet_id), record.external_id, record.display_name, record.model_name, _utc(record.created_at_utc))


def _case(record: InspectionCaseRecord) -> InspectionCase:
    return InspectionCase(
        id=str(record.id),
        tractor_id=str(record.tractor_id),
        status=_status(record.status),
        version=record.version,
        assignee=record.assignee,
        due_date=record.due_date.isoformat() if record.due_date is not None else None,
        evidence_as_of_utc=_utc(record.evidence_as_of_utc),
        snapshot_schema_version=_snapshot_schema_version(record.snapshot_schema_version),
        evidence_snapshot=dict(record.evidence_snapshot),
        evidence_sha256=record.evidence_sha256,
        result=_result(record.result),
        result_notes=record.result_notes,
        created_at_utc=_utc(record.created_at_utc),
        updated_at_utc=_utc(record.updated_at_utc),
        started_at_utc=_optional_utc(record.started_at_utc),
        completed_at_utc=_optional_utc(record.completed_at_utc),
        cancelled_at_utc=_optional_utc(record.cancelled_at_utc),
        findings=_findings(record.findings),
    )


def _case_event(record: InspectionCaseEventRecord) -> InspectionCaseEvent:
    return InspectionCaseEvent(
        id=str(record.id),
        case_id=str(record.case_id),
        action=_event_action(record.action),
        actor_user_id=str(record.actor_user_id),
        actor_worker_id=record.actor_worker_id,
        actor_role=record.actor_role,
        occurred_at_utc=_utc(record.occurred_at_utc),
        prior_status=_status(record.prior_status) if record.prior_status is not None else None,
        new_status=_status(record.new_status),
        case_version=record.case_version,
        details=dict(record.details),
    )


def _event_action(value: str) -> InspectionCaseEventAction:
    if value == "SAVE_DRAFT":
        return "SAVE_DRAFT"
    if value == "CREATE":
        return "CREATE"
    if value == "UPDATE":
        return "UPDATE"
    if value == "START":
        return "START"
    if value == "COMPLETE":
        return "COMPLETE"
    if value == "CANCEL":
        return "CANCEL"
    raise ValueError("persisted inspection case event has an unsupported action")


def _findings_storage(
    values: tuple[InspectionFinding, ...] | None,
) -> list[dict[str, object]] | None:
    if values is None:
        return None
    return [
        {"item_id": value.item_id, "status": value.status, "notes": value.notes}
        for value in values
    ]


def _findings(values: list[dict[str, object]] | None) -> tuple[InspectionFinding, ...] | None:
    if values is None:
        return None
    return tuple(
        InspectionFinding(
            item_id=str(value["item_id"]),
            status=_finding_status(value["status"]),
            notes=str(value["notes"]) if value.get("notes") is not None else None,
        )
        for value in values
    )


def _finding_status(value: object) -> InspectionFindingStatus:
    if value == "OK":
        return "OK"
    if value == "ATTENTION":
        return "ATTENTION"
    if value == "PROBLEM":
        return "PROBLEM"
    if value == "NOT_CHECKED":
        return "NOT_CHECKED"
    raise ValueError("persisted inspection finding has an unsupported status")


def _status(value: str) -> InspectionCaseStatus:
    if value == "OPEN":
        return "OPEN"
    if value == "IN_PROGRESS":
        return "IN_PROGRESS"
    if value == "COMPLETED":
        return "COMPLETED"
    if value == "CANCELLED":
        return "CANCELLED"
    raise ValueError("persisted inspection case has an unsupported status")


def _snapshot_schema_version(value: str) -> InspectionSnapshotSchemaVersion:
    if value == "inspection-evidence-v1":
        return "inspection-evidence-v1"
    if value == "inspection-evidence-v2":
        return "inspection-evidence-v2"
    raise ValueError("persisted inspection case has an unsupported snapshot schema")


def _result(value: str | None) -> InspectionCaseResult | None:
    if value is None:
        return None
    if value == "NO_ACTION":
        return "NO_ACTION"
    if value == "MONITOR":
        return "MONITOR"
    if value == "MAINTENANCE_RECOMMENDED":
        return "MAINTENANCE_RECOMMENDED"
    raise ValueError("persisted inspection case has an unsupported result")
