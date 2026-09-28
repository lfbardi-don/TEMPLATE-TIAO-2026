from __future__ import annotations

from contextlib import nullcontext
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from tractor_usage.api import routes
from tractor_usage.api.app import create_app
from tractor_usage.api.auth import Principal, current_user
from tractor_usage.application.contracts import Fleet, InspectionCase, Tractor
from tractor_usage.application.use_cases import GetPortfolioPrioritiesUseCase


FLEET_A = "11111111-1111-4111-8111-111111111111"
FLEET_B = "22222222-2222-4222-8222-222222222222"
TRACTOR_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
TRACTOR_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
CASE_A = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
CASE_B = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
NOW = datetime(2026, 8, 24, tzinfo=timezone.utc)


class _InspectionRepository:
    def __init__(self) -> None:
        self.fleets = {
            FLEET_A: Fleet(FLEET_A, "Fleet A", NOW),
            FLEET_B: Fleet(FLEET_B, "Fleet B", NOW),
        }
        self.tractors = {
            TRACTOR_A: Tractor(TRACTOR_A, FLEET_A, "A", None, "Fendt 314", NOW),
            TRACTOR_B: Tractor(TRACTOR_B, FLEET_B, "B", None, "Fendt 314", NOW),
        }

    def get_fleet(self, fleet_id: str):
        return self.fleets.get(fleet_id)

    def get_tractor(self, tractor_id: str, *, for_update: bool = False):
        return self.tractors.get(tractor_id)


def _case(case_id: str, tractor_id: str) -> InspectionCase:
    return InspectionCase(
        id=case_id,
        tractor_id=tractor_id,
        status="OPEN",
        version=1,
        assignee="Field team",
        due_date="2026-08-30",
        evidence_as_of_utc=NOW,
        snapshot_schema_version="inspection-evidence-v1",
        evidence_snapshot={},
        evidence_sha256="a" * 64,
        result=None,
        result_notes=None,
        created_at_utc=NOW,
        updated_at_utc=NOW,
        started_at_utc=None,
        completed_at_utc=None,
        cancelled_at_utc=None,
    )


class _Cases:
    def __init__(self) -> None:
        self.cases = {CASE_A: _case(CASE_A, TRACTOR_A), CASE_B: _case(CASE_B, TRACTOR_B)}
        self.events = {CASE_A: [], CASE_B: []}

    def transaction(self):
        return nullcontext()

    def get_tractor(self, tractor_id: str, *, for_update: bool = False):
        return _InspectionRepository().tractors.get(tractor_id)

    def get_case(self, case_id: str, *, for_update: bool = False):
        return self.cases.get(case_id)

    def list_cases(self, tractor_id: str | None = None):
        return tuple(case for case in self.cases.values() if tractor_id is None or case.tractor_id == tractor_id)

    def update_case(self, value: InspectionCase):
        self.cases[value.id] = value
        return value

    def append_event(self, value):
        self.events[value.case_id].append(value)

    def list_events(self, case_id: str):
        return tuple(self.events[case_id])


def _principal(role: str, fleet_id: str | None = None) -> Principal:
    worker_ids = {"ADMIN": "000001", "INSURER": "100001", "INSPECTOR": "200001", "FLEET_MANAGER": "300001"}
    return Principal(id=f"{role.lower()}-1", worker_id=worker_ids[role], role=role, fleet_id=fleet_id)


def _app(monkeypatch, principal: Principal, repository: _InspectionRepository, cases: _Cases):
    app = create_app(usage_model=object(), engine=create_engine("sqlite://"))
    app.dependency_overrides[current_user] = lambda: principal
    app.dependency_overrides[routes.request_session] = lambda: object()
    monkeypatch.setattr(routes, "PostgresInspectionRepository", lambda _: repository)
    monkeypatch.setattr(routes, "PostgresInspectionCaseRepository", lambda _: cases)
    monkeypatch.setattr(routes, "inspection_case_response", lambda value: {"id": value.id, "status": value.status})
    monkeypatch.setattr(routes, "AuthRepository", lambda _: _InspectorDirectory())
    return app


class _InspectorDirectory:
    def list_active_inspectors(self):
        return (_principal("INSPECTOR"),)

    def is_active_inspector(self, worker_id: str) -> bool:
        return worker_id == "200001"


def test_business_routes_require_login_but_health_remains_public() -> None:
    app = create_app(usage_model=object(), engine=create_engine("sqlite://"))

    with TestClient(app) as client:
        assert client.get("/health/live").status_code == 200
        assert client.get("/v1/portfolio/inspection-priorities").status_code == 401
        assert client.get(f"/v1/tractors/{TRACTOR_A}/overview").status_code == 401
        assert client.get(f"/v1/inspection-cases/{CASE_A}").status_code == 401
        assert client.get(f"/v1/inspection-cases/{CASE_A}/events").status_code == 401
        assert client.get("/v1/inspectors").status_code == 401
        assert client.get("/v1/demo/replay-progress").status_code == 401
        assert client.post("/v1/fleets", json={"name": "Fleet C", "tractors": [{"external_id": "C"}]}).status_code == 401


def test_manager_can_read_own_machine_but_foreign_ids_are_hidden(monkeypatch) -> None:
    repository = _InspectionRepository()
    cases = _Cases()
    app = _app(monkeypatch, _principal("FLEET_MANAGER", FLEET_A), repository, cases)

    class _UseCase:
        def __init__(self, *args):
            pass

        def execute(self, resource_id, *args, **kwargs):
            return resource_id

    monkeypatch.setattr(routes, "GetTractorOverviewUseCase", _UseCase)
    monkeypatch.setattr(routes, "tractor_overview_response", lambda value: {"id": value})
    monkeypatch.setattr(routes, "GetFleetOverviewUseCase", _UseCase)
    monkeypatch.setattr(routes, "fleet_overview_response", lambda value: {"id": value})
    monkeypatch.setattr(routes, "GetEpisodeDetailUseCase", _UseCase)
    monkeypatch.setattr(routes, "episode_detail_response", lambda value: {"id": value})
    monkeypatch.setattr(routes, "GetExposureTimelineUseCase", _UseCase)
    monkeypatch.setattr(routes, "exposure_timeline_response", lambda value: {"id": value})

    with TestClient(app) as client:
        assert client.get(f"/v1/tractors/{TRACTOR_A}/overview").status_code == 200
        assert client.get(f"/v1/tractors/{TRACTOR_B}/overview").status_code == 404
        assert client.get(f"/v1/fleets/{FLEET_A}/overview").status_code == 200
        assert client.get(f"/v1/fleets/{FLEET_B}/overview").status_code == 404
        assert client.get(f"/v1/tractors/{TRACTOR_A}/episodes/{'a' * 20}").status_code == 200
        assert client.get(f"/v1/tractors/{TRACTOR_B}/episodes/{'a' * 20}").status_code == 404
        assert client.get(f"/v1/tractors/{TRACTOR_A}/exposure-timeline").status_code == 200
        assert client.get(f"/v1/tractors/{TRACTOR_B}/exposure-timeline").status_code == 404
        assert client.get(f"/v1/tractors/{TRACTOR_A}/telemetry-periods").status_code == 403
        assert client.get(f"/v1/tractors/{TRACTOR_B}/telemetry-periods").status_code == 404
        assert client.get(f"/v1/tractors/{TRACTOR_A}/inspection-cases").status_code == 403
        assert client.get(f"/v1/tractors/{TRACTOR_B}/inspection-cases").status_code == 404
        assert client.get(f"/v1/inspection-cases/{CASE_A}").status_code == 403
        assert client.get(f"/v1/inspection-cases/{CASE_B}").status_code == 404
        assert client.get(f"/v1/inspection-cases/{CASE_A}/events").status_code == 403
        assert client.get(f"/v1/inspection-cases/{CASE_B}/events").status_code == 404
        assert client.get("/v1/inspectors").status_code == 403
        assert client.post(f"/v1/tractors/{TRACTOR_A}/inspection-cases", json={}).status_code == 403
        assert client.post(f"/v1/tractors/{TRACTOR_B}/inspection-cases", json={}).status_code == 404
        assert client.patch(f"/v1/inspection-cases/{CASE_A}", json={"version": 1, "action": "START"}).status_code == 403
        assert client.patch(f"/v1/inspection-cases/{CASE_B}", json={"version": 1, "action": "START"}).status_code == 404
        assert client.post("/v1/fleets", json={"name": "Fleet C", "tractors": [{"external_id": "C"}]}).status_code == 403


def test_case_actions_and_inspector_metadata_are_enforced(monkeypatch) -> None:
    repository = _InspectionRepository()
    cases = _Cases()
    app = _app(monkeypatch, _principal("INSPECTOR"), repository, cases)

    with TestClient(app) as client:
        assert client.get(f"/v1/inspection-cases/{CASE_A}").status_code == 200
        assert client.get(f"/v1/inspection-cases/{CASE_A}/events").status_code == 403
        assert client.get("/v1/inspectors").status_code == 403
        assert client.get(f"/v1/fleets/{FLEET_A}/overview").status_code == 403
        assert client.get(f"/v1/tractors/{TRACTOR_A}/telemetry-periods").status_code == 403
        assert client.patch(f"/v1/inspection-cases/{CASE_A}", json={"version": 1, "action": "UPDATE", "assignee": "Other"}).status_code == 403
        assert client.patch(f"/v1/inspection-cases/{CASE_A}", json={"version": 1, "action": "CANCEL"}).status_code == 403
        assert client.patch(f"/v1/inspection-cases/{CASE_A}", json={"version": 1, "action": "START", "assignee": "Other"}).status_code == 403
        assert client.patch(f"/v1/inspection-cases/{CASE_A}", json={"version": 1, "action": "START", "due_date": "2026-09-01"}).status_code == 403
        started = client.patch(
            f"/v1/inspection-cases/{CASE_A}",
            json={"version": 1, "action": "START", "assignee": "Field team", "due_date": "2026-08-30"},
        )
        assert started.status_code == 200
        assert started.json()["status"] == "IN_PROGRESS"
        completed = client.patch(
            f"/v1/inspection-cases/{CASE_A}",
            json={"version": 2, "action": "COMPLETE", "result": "MONITOR", "result_notes": "Inspect again next month."},
        )
        assert completed.status_code == 200
        assert completed.json()["status"] == "COMPLETED"
        assert client.get(f"/v1/inspection-cases/{CASE_A}/events").status_code == 403

    app.dependency_overrides[current_user] = lambda: _principal("INSURER")
    with TestClient(app) as client:
        inspectors = client.get("/v1/inspectors")
        assert inspectors.status_code == 200
        assert inspectors.headers["cache-control"] == "no-store"
        assert inspectors.json() == {"inspectors": [{"id": "inspector-1", "worker_id": "200001"}]}
        assert client.get(f"/v1/inspection-cases/{CASE_A}/events").status_code == 403
        assert client.patch(f"/v1/inspection-cases/{CASE_B}", json={"version": 1, "action": "START"}).status_code == 403
        assert client.patch(
            f"/v1/inspection-cases/{CASE_B}",
            json={"version": 1, "action": "UPDATE", "assignee": "New team"},
        ).status_code == 422
        updated = client.patch(f"/v1/inspection-cases/{CASE_B}", json={"version": 1, "action": "UPDATE", "assignee": "200001"})
        assert updated.status_code == 200
        assert cases.cases[CASE_B].assignee == "200001"
        cancelled = client.patch(f"/v1/inspection-cases/{CASE_B}", json={"version": 2, "action": "CANCEL"})
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "CANCELLED"
        assert client.get(f"/v1/inspection-cases/{CASE_B}/events").status_code == 403

    app.dependency_overrides[current_user] = lambda: _principal("ADMIN")
    with TestClient(app) as client:
        history = client.get(f"/v1/inspection-cases/{CASE_B}/events").json()["events"]
        assert [event["action"] for event in history] == ["UPDATE", "CANCEL"]
        assert history[0]["details"]["changes"]["assignee"] == {
            "from": "Field team", "to": "200001"
        }
        assert [event["action"] for event in client.get(f"/v1/inspection-cases/{CASE_A}/events").json()["events"]] == ["START", "COMPLETE"]


def test_insurer_can_create_case_with_active_inspector_or_no_assignee(monkeypatch) -> None:
    repository = _InspectionRepository()
    app = _app(monkeypatch, _principal("INSURER"), repository, _Cases())
    accepted: list[str | None] = []

    class _CreateCase:
        def __init__(self, *args):
            pass

        def execute(self, tractor_id, request, *, authorize_tractor, actor):
            authorize_tractor(repository.tractors[tractor_id])
            accepted.append(request.assignee)
            return replace(_case(CASE_A, tractor_id), assignee=request.assignee)

    monkeypatch.setattr(routes, "CreateInspectionCaseUseCase", _CreateCase)

    with TestClient(app) as client:
        url = f"/v1/tractors/{TRACTOR_A}/inspection-cases"
        assert client.post(url, json={"assignee": "Field team"}).status_code == 422
        assert client.post(url, json={"assignee": "200001"}).status_code == 201
        assert client.post(url, json={"assignee": None}).status_code == 201
        assert accepted == ["200001", None]


def test_admin_reads_global_evidence_and_case_history_without_case_write_access(monkeypatch) -> None:
    app = _app(monkeypatch, _principal("ADMIN"), _InspectionRepository(), _Cases())

    class _UseCase:
        def __init__(self, *args):
            pass

        def execute(self, resource_id, *args, **kwargs):
            return resource_id

    monkeypatch.setattr(routes, "GetFleetOverviewUseCase", _UseCase)
    monkeypatch.setattr(routes, "fleet_overview_response", lambda value: {"id": value})
    monkeypatch.setattr(routes, "GetTelemetryPeriodsUseCase", _UseCase)
    monkeypatch.setattr(routes, "telemetry_periods_response", lambda value: {"id": value})

    with TestClient(app) as client:
        assert client.get("/v1/inspectors").json() == {
            "inspectors": [{"id": "inspector-1", "worker_id": "200001"}]
        }
        assert client.get(f"/v1/fleets/{FLEET_B}/overview").status_code == 200
        assert client.get(f"/v1/tractors/{TRACTOR_B}/telemetry-periods").status_code == 200
        assert client.get(f"/v1/tractors/{TRACTOR_B}/inspection-cases").status_code == 200
        assert client.get(f"/v1/inspection-cases/{CASE_B}").status_code == 200
        assert client.get(f"/v1/inspection-cases/{CASE_B}/events").json()["events"] == []
        assert client.post(f"/v1/tractors/{TRACTOR_B}/inspection-cases", json={}).status_code == 403
        assert client.patch(
            f"/v1/inspection-cases/{CASE_B}", json={"version": 1, "action": "START"}
        ).status_code == 403
        assert client.patch(
            f"/v1/inspection-cases/{CASE_B}", json={"version": 1, "action": "CANCEL"}
        ).status_code == 403


def test_demo_progress_and_portfolio_use_manager_fleet_scope(monkeypatch) -> None:
    repository = _InspectionRepository()
    app = _app(monkeypatch, _principal("FLEET_MANAGER", FLEET_A), repository, _Cases())
    scoped_fleets: list[str | None] = []

    class _Portfolio:
        def __init__(self, *args):
            pass

        def execute(self, *, fleet_id=None, as_of_utc=None):
            scoped_fleets.append(fleet_id)
            return fleet_id

    monkeypatch.setattr(routes, "GetPortfolioPrioritiesUseCase", _Portfolio)
    monkeypatch.setattr(routes, "portfolio_response", lambda value: {"fleet_id": value})
    monkeypatch.setattr(routes, "replay_progress_response", lambda value: {"tractor_id": value.tractor_id})

    class _Reader:
        def __init__(self, tractor_id: str):
            self.tractor_id = tractor_id

        def snapshot(self):
            return SimpleNamespace(tractor_id=self.tractor_id)

    app.state.replay_progress = _Reader(TRACTOR_B)
    with TestClient(app) as client:
        assert client.get("/v1/portfolio/inspection-priorities").json() == {"fleet_id": FLEET_A}
        assert client.get("/v1/demo/replay-progress").status_code == 404
        app.state.replay_progress = _Reader(TRACTOR_A)
        assert client.get("/v1/demo/replay-progress").json() == {"tractor_id": TRACTOR_A}
    assert scoped_fleets == [FLEET_A]


def test_scoped_portfolio_uses_only_its_fleet_for_as_of_and_tractors() -> None:
    repository = _InspectionRepository()
    seen: list[tuple[str, str | None]] = []

    class _PortfolioRepository:
        def latest_window_close(self, *, tractor_id=None, fleet_id=None):
            seen.append(("latest", fleet_id))
            return NOW if fleet_id == FLEET_A else NOW + timedelta(days=30)

        def list_tractors(self, *, fleet_id=None):
            seen.append(("tractors", fleet_id))
            return tuple(
                tractor for tractor in repository.tractors.values()
                if fleet_id is None or tractor.fleet_id == fleet_id
            )

        def get_fleet_for_tractor(self, tractor_id):
            return repository.fleets[repository.tractors[tractor_id].fleet_id]

        def list_report_windows(self, tractor_id, *, as_of_utc):
            return ()

    result = GetPortfolioPrioritiesUseCase(_PortfolioRepository(), object()).execute(fleet_id=FLEET_A)

    assert result.as_of_utc == NOW
    assert [priority.tractor.id for priority in result.priorities] == [TRACTOR_A]
    assert seen == [("latest", FLEET_A), ("tractors", FLEET_A)]


def test_global_cases_and_saved_findings_follow_role_access(monkeypatch) -> None:
    cases = _Cases()
    cases.cases[CASE_A] = replace(
        cases.cases[CASE_A], status="IN_PROGRESS", started_at_utc=NOW,
        snapshot_schema_version="inspection-evidence-v2",
        evidence_snapshot={"inspection_agenda": {"items": [{"id": "engine"}]}},
    )
    app = _app(monkeypatch, _principal("FLEET_MANAGER", FLEET_A), _InspectionRepository(), cases)
    with TestClient(app) as client:
        assert client.get("/v1/inspection-cases").status_code == 403
        payload = {"version": 1, "action": "SAVE_DRAFT", "findings": [{"item_id": "engine", "status": "OK"}]}
        for role in ("ADMIN", "INSURER"):
            app.dependency_overrides[current_user] = lambda role=role: _principal(role)
            assert len(client.get("/v1/inspection-cases").json()["cases"]) == 2
            assert client.patch(f"/v1/inspection-cases/{CASE_A}", json=payload).status_code == 403
        app.dependency_overrides[current_user] = lambda: _principal("INSPECTOR")
        assert client.get("/v1/inspection-cases").status_code == 200
        assert client.patch(f"/v1/inspection-cases/{CASE_A}", json=payload).status_code == 200
        assert cases.cases[CASE_A].version == 2
        assert cases.events[CASE_A][0].action == "SAVE_DRAFT"
        assert cases.events[CASE_A][0].actor_worker_id == "200001"


def test_case_episode_uses_frozen_cutoff_and_rejects_unrelated_evidence(monkeypatch) -> None:
    cases = _Cases()
    episode_id = "a" * 20
    cases.cases[CASE_A] = replace(
        cases.cases[CASE_A], evidence_snapshot={"episodes_last_30_days": [{"id": episode_id}]}
    )
    app = _app(monkeypatch, _principal("INSPECTOR"), _InspectionRepository(), cases)
    called = []
    class Episode:
        def __init__(self, *args):
            pass

        def execute(self, tractor_id, id, *, as_of_utc):
            called.append((tractor_id, id, as_of_utc))
            return {}

    monkeypatch.setattr(routes, "GetEpisodeDetailUseCase", Episode)
    monkeypatch.setattr(routes, "episode_detail_response", lambda value: value)
    with TestClient(app) as client:
        assert client.get(f"/v1/inspection-cases/{CASE_A}/episodes/{episode_id}").status_code == 200
        assert called == [(TRACTOR_A, episode_id, NOW)]
        assert client.get(f"/v1/inspection-cases/{CASE_A}/episodes/{'b' * 20}").status_code == 404
        app.dependency_overrides[current_user] = lambda: _principal("FLEET_MANAGER", FLEET_A)
        assert client.get(f"/v1/inspection-cases/{CASE_A}/episodes/{episode_id}").status_code == 403
