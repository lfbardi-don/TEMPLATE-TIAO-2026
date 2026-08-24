from __future__ import annotations

from contextlib import nullcontext
from datetime import datetime, timezone

import pytest

from tractor_usage.application.contracts import (
    InspectionCase,
    InvalidInspectionTransitionError,
    StaleInspectionCaseVersionError,
    UpdateInspectionCase,
)
from tractor_usage.application.inspection_cases import UpdateInspectionCaseUseCase


UTC = timezone.utc


class _Cases:
    def __init__(self, value: InspectionCase) -> None:
        self.value = value

    def transaction(self):
        return nullcontext()

    def get_case(self, _: str, *, for_update: bool = False) -> InspectionCase:
        return self.value

    def update_case(self, value: InspectionCase) -> InspectionCase:
        self.value = value
        return value


def _case(status: str = "OPEN") -> InspectionCase:
    now = datetime(2026, 8, 23, tzinfo=UTC)
    return InspectionCase(
        id="case-1", tractor_id="tractor-1", status=status, version=1,
        assignee="Equipe de campo", due_date="2026-08-30",
        evidence_as_of_utc=now, snapshot_schema_version="inspection-evidence-v1", evidence_snapshot={}, evidence_sha256="a" * 64,
        result=None, result_notes=None, created_at_utc=now, updated_at_utc=now,
        started_at_utc=None, completed_at_utc=None, cancelled_at_utc=None,
    )


def test_case_transitions_are_versioned_and_terminal_cases_are_immutable() -> None:
    repository = _Cases(_case())
    use_case = UpdateInspectionCaseUseCase(repository)

    started = use_case.execute("case-1", UpdateInspectionCase(version=1, action="START"))
    completed = use_case.execute(
        "case-1",
        UpdateInspectionCase(version=2, action="COMPLETE", result="MONITOR", result_notes="Revisar no próximo ciclo."),
    )

    assert started.status == "IN_PROGRESS"
    assert started.version == 2
    assert started.assignee == "Equipe de campo"
    assert started.due_date == "2026-08-30"
    assert completed.status == "COMPLETED"
    assert completed.version == 3
    assert completed.assignee == "Equipe de campo"
    assert completed.due_date == "2026-08-30"
    assert completed.evidence_sha256 == "a" * 64
    with pytest.raises(InvalidInspectionTransitionError):
        use_case.execute("case-1", UpdateInspectionCase(version=3, action="CANCEL"))


def test_case_rejects_stale_version_before_transition() -> None:
    use_case = UpdateInspectionCaseUseCase(_Cases(_case()))

    with pytest.raises(StaleInspectionCaseVersionError):
        use_case.execute("case-1", UpdateInspectionCase(version=2, action="START"))


def test_metadata_update_distinguishes_omitted_fields_from_explicit_null() -> None:
    repository = _Cases(_case())
    use_case = UpdateInspectionCaseUseCase(repository)

    reassigned = use_case.execute(
        "case-1",
        UpdateInspectionCase(
            version=1,
            action="UPDATE",
            assignee="Nova equipe",
            assignee_present=True,
        ),
    )
    cleared_due_date = use_case.execute(
        "case-1",
        UpdateInspectionCase(
            version=2,
            action="UPDATE",
            due_date=None,
            due_date_present=True,
        ),
    )

    assert reassigned.assignee == "Nova equipe"
    assert reassigned.due_date == "2026-08-30"
    assert cleared_due_date.assignee == "Nova equipe"
    assert cleared_due_date.due_date is None
