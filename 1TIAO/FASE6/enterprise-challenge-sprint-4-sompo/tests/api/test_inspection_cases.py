from __future__ import annotations

from contextlib import nullcontext
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from tractor_usage.application.contracts import (
    InspectionCase,
    InspectionFinding,
    ConflictError,
    CreateInspectionCase,
    InvalidInspectionTransitionError,
    StaleInspectionCaseVersionError,
    UpdateInspectionCase,
)
from tractor_usage.application.inspection_cases import CreateInspectionCaseUseCase, UpdateInspectionCaseUseCase
from tractor_usage.application.inspection_workflow import inspection_workflow


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


def _v2_case(item_ids: tuple[str, ...] = ("engine", "cooling")) -> InspectionCase:
    return replace(
        _case("IN_PROGRESS"),
        started_at_utc=datetime(2026, 8, 24, tzinfo=UTC),
        snapshot_schema_version="inspection-evidence-v2",
        evidence_snapshot={
            "inspection_agenda": {
                "version": "inspection-checklist-v1",
                "validation_status": "engineering_hypothesis",
                "items": [{"id": item_id} for item_id in item_ids],
            }
        },
    )


def _complete(findings: tuple[InspectionFinding, ...] | None) -> UpdateInspectionCase:
    return UpdateInspectionCase(
        version=1,
        action="COMPLETE",
        result="MAINTENANCE_RECOMMENDED",
        result_notes="Filtro de ar saturado.",
        findings=findings,
    )


def test_completing_a_v2_case_records_one_finding_per_agenda_item_in_agenda_order() -> None:
    repository = _Cases(_v2_case())

    completed = UpdateInspectionCaseUseCase(repository).execute(
        "case-1",
        _complete(
            (
                InspectionFinding("cooling", "OK", "  "),
                InspectionFinding("engine", "PROBLEM", " Vazamento no cárter. "),
            )
        ),
    )

    assert completed.status == "COMPLETED"
    assert completed.findings == (
        InspectionFinding("engine", "PROBLEM", "Vazamento no cárter."),
        InspectionFinding("cooling", "OK", None),
    )


@pytest.mark.parametrize(
    "findings",
    [
        None,
        (InspectionFinding("engine", "OK", None),),
        (
            InspectionFinding("engine", "OK", None),
            InspectionFinding("engine", "OK", None),
            InspectionFinding("cooling", "OK", None),
        ),
        (
            InspectionFinding("engine", "OK", None),
            InspectionFinding("cooling", "OK", None),
            InspectionFinding("tires_ballast", "OK", None),
        ),
        (
            InspectionFinding("engine", "ATTENTION", None),
            InspectionFinding("cooling", "OK", None),
        ),
    ],
)
def test_completing_a_v2_case_rejects_incomplete_or_unexplained_findings(findings) -> None:
    use_case = UpdateInspectionCaseUseCase(_Cases(_v2_case()))

    with pytest.raises(InvalidInspectionTransitionError):
        use_case.execute("case-1", _complete(findings))


def test_v2_case_without_agenda_items_completes_with_empty_findings() -> None:
    completed = UpdateInspectionCaseUseCase(_Cases(_v2_case(()))).execute(
        "case-1", _complete(None)
    )

    assert completed.findings == ()


def test_findings_are_rejected_outside_completion_and_on_v1_cases() -> None:
    finding = (InspectionFinding("engine", "OK", None),)

    with pytest.raises(InvalidInspectionTransitionError):
        UpdateInspectionCaseUseCase(_Cases(_case())).execute(
            "case-1", UpdateInspectionCase(version=1, action="START", findings=finding)
        )
    with pytest.raises(InvalidInspectionTransitionError):
        UpdateInspectionCaseUseCase(
            _Cases(replace(_case("IN_PROGRESS"), started_at_utc=datetime(2026, 8, 24, tzinfo=UTC)))
        ).execute("case-1", _complete(finding))


def test_partial_draft_survives_metadata_update_and_requires_version_and_complete_agenda() -> None:
    repository = _Cases(_v2_case())
    use_case = UpdateInspectionCaseUseCase(repository)
    draft = use_case.execute("case-1", UpdateInspectionCase(
        version=1, action="SAVE_DRAFT",
        findings=(InspectionFinding("engine", "ATTENTION", " Conferir vazamento. "),),
    ))
    assert draft.status == "IN_PROGRESS"
    assert draft.version == 2
    assert draft.findings == (InspectionFinding("engine", "ATTENTION", "Conferir vazamento."),)
    assert draft.evidence_snapshot == _v2_case().evidence_snapshot
    with pytest.raises(StaleInspectionCaseVersionError):
        use_case.execute("case-1", UpdateInspectionCase(version=1, action="SAVE_DRAFT", findings=()))
    updated = use_case.execute("case-1", UpdateInspectionCase(version=2, action="UPDATE", due_date_present=True))
    assert updated.findings == draft.findings
    with pytest.raises(InvalidInspectionTransitionError, match="each agenda item"):
        use_case.execute("case-1", replace(_complete(draft.findings), version=3))
    cleared = use_case.execute("case-1", UpdateInspectionCase(version=3, action="SAVE_DRAFT", findings=()))
    assert cleared.findings == ()


def test_draft_rejects_unknown_agenda_items_and_requires_notes() -> None:
    use_case = UpdateInspectionCaseUseCase(_Cases(_v2_case()))
    for findings in (
        (InspectionFinding("other", "OK", None),),
        (InspectionFinding("engine", "PROBLEM", None),),
    ):
        with pytest.raises(InvalidInspectionTransitionError):
            use_case.execute("case-1", UpdateInspectionCase(version=1, action="SAVE_DRAFT", findings=findings))
    for case in (_case(), replace(_v2_case(), status="OPEN"), replace(_v2_case(), status="COMPLETED")):
        with pytest.raises(InvalidInspectionTransitionError):
            UpdateInspectionCaseUseCase(_Cases(case)).execute(
                "case-1", UpdateInspectionCase(version=1, action="SAVE_DRAFT", findings=())
            )


def test_workflow_distinguishes_inspected_evidence_using_the_first_window_close() -> None:
    completed = replace(_v2_case(), status="COMPLETED", result="MONITOR", completed_at_utc=datetime(2026, 8, 25, tzinfo=UTC))
    cutoff = completed.evidence_as_of_utc
    episodes = (
        SimpleNamespace(id="reviewed", started_at_utc=cutoff - timedelta(seconds=60)),
        SimpleNamespace(id="new", started_at_utc=cutoff),
    )
    workflow = inspection_workflow((completed,), episodes)
    assert workflow["new_episode_ids"] == ["new"]
    assert workflow["last_completed_case"]["result"] == "MONITOR"
    assert workflow["can_open_case"] is True
    assert inspection_workflow((completed,), episodes[:1])["can_open_case"] is False
    assert inspection_workflow((completed, _case()), episodes)["can_open_case"] is False


def test_create_refuses_reopening_the_same_completed_evidence(monkeypatch) -> None:
    completed = replace(_v2_case(), status="COMPLETED")
    overview = SimpleNamespace(episodes_last_30_days=(
        SimpleNamespace(id="reviewed", started_at_utc=completed.evidence_as_of_utc - timedelta(seconds=60)),
    ))
    class Cases(_Cases):
        def get_tractor(self, *_args, **_kwargs):
            return object()

        def find_active_case(self, _tractor_id):
            return None

        def list_cases(self, _tractor_id):
            return (completed,)

    monkeypatch.setattr(
        "tractor_usage.application.inspection_cases.GetTractorOverviewUseCase.execute",
        lambda *args, **kwargs: overview,
    )
    with pytest.raises(ConflictError, match="no new episodes"):
        CreateInspectionCaseUseCase(Cases(completed), object(), object(), object()).execute(
            "tractor-1", CreateInspectionCase(assignee=None, due_date=None)
        )
