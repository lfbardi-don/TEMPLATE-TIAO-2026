"""PostgreSQL persistence for immutable-evidence inspection cases."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timezone
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tractor_usage.application.contracts import (
    ConflictError,
    Fleet,
    InspectionCase,
    InspectionCaseResult,
    InspectionCaseStatus,
    Tractor,
)
from tractor_usage.infrastructure.models import FleetRecord, InspectionCaseRecord, TractorRecord


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

    def get_fleet_for_tractor(self, tractor_id: str) -> Fleet | None:
        record = self._session.scalar(
            select(FleetRecord)
            .join(TractorRecord, TractorRecord.fleet_id == FleetRecord.id)
            .where(TractorRecord.id == _uuid(tractor_id))
        )
        return _fleet(record) if record is not None else None

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

    def list_cases(self, tractor_id: str) -> tuple[InspectionCase, ...]:
        return tuple(
            _case(record)
            for record in self._session.scalars(
                select(InspectionCaseRecord)
                .where(InspectionCaseRecord.tractor_id == _uuid(tractor_id))
                .order_by(InspectionCaseRecord.created_at_utc.desc(), InspectionCaseRecord.id.desc())
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
        record.updated_at_utc = _utc(value.updated_at_utc)
        record.started_at_utc = _optional_utc(value.started_at_utc)
        record.completed_at_utc = _optional_utc(value.completed_at_utc)
        record.cancelled_at_utc = _optional_utc(value.cancelled_at_utc)
        # Snapshot and evidence hash are intentionally never assigned here.
        self._session.flush()
        return _case(record)


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


def _fleet(record: FleetRecord) -> Fleet:
    return Fleet(str(record.id), record.name, _utc(record.created_at_utc))


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
    )


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


def _snapshot_schema_version(value: str) -> Literal["inspection-evidence-v1"]:
    if value != "inspection-evidence-v1":
        raise ValueError("persisted inspection case has an unsupported snapshot schema")
    return "inspection-evidence-v1"


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
