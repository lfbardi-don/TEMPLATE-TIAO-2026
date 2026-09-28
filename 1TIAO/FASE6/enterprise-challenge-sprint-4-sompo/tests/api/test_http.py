from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from tractor_usage.api.app import create_app
from tractor_usage.api.auth import Principal, current_user
from tractor_usage.application.contracts import (
    ConflictError,
    Fleet,
    FleetRegistration,
    ModelUnavailableError,
    NotFoundError,
    RecentReplayInference,
    ReplayProgressSnapshot,
    Tractor,
)
from tractor_usage.infrastructure.database import Settings


INSURER = Principal(id="insurer-1", worker_id="100001", role="INSURER", fleet_id=None)


def test_liveness_is_dependency_free_and_readiness_reflects_database_connection() -> None:
    app = create_app(usage_model=object(), engine=create_engine("sqlite://"))

    @app.get("/_test/failure/{kind}")
    def failure(kind: str):
        if kind == "missing":
            raise NotFoundError("internal detail must not be exposed")
        if kind == "conflict":
            raise ConflictError("internal detail must not be exposed")
        raise ModelUnavailableError("internal detail must not be exposed")

    with TestClient(app) as client:
        assert client.get("/health/live").json() == {"status": "live"}
        assert client.get("/health/ready").json() == {"status": "ready"}
        assert client.get("/_test/failure/missing").status_code == 404
        assert client.get("/_test/failure/conflict").status_code == 409
        assert client.get("/_test/failure/model").status_code == 500


def test_invalid_resource_identifiers_are_rejected_at_the_http_boundary() -> None:
    app = create_app(usage_model=object(), engine=create_engine("sqlite://"))
    app.dependency_overrides[current_user] = lambda: INSURER

    with TestClient(app) as client:
        assert client.get("/v1/fleets/not-a-uuid/overview").status_code == 422
        assert client.get("/v1/tractors/not-a-uuid/overview").status_code == 422


def test_demo_progress_route_returns_no_content_by_default_and_projects_only_injected_state(monkeypatch) -> None:
    from tractor_usage.api import routes

    class _Repository:
        def get_tractor(self, tractor_id: str):
            return object() if tractor_id == "tractor-id" else None

    monkeypatch.setattr(routes, "PostgresInspectionRepository", lambda _: _Repository())
    default_app = create_app(usage_model=object(), engine=create_engine("sqlite://"))
    default_app.dependency_overrides[current_user] = lambda: INSURER
    with TestClient(default_app) as client:
        response = client.get("/v1/demo/replay-progress")
        assert response.status_code == 204
        assert response.content == b""

    class Reader:
        def snapshot(self) -> ReplayProgressSnapshot:
            return ReplayProgressSnapshot(
                status="running",
                tractor_id="tractor-id",
                telemetry_import_id="import-id",
                dataset_split="validation",
                source_doi="10.5281/zenodo.14619787",
                source_license="CC-BY-4.0",
                semantic_sha256="a" * 64,
                total_samples=152_561,
                samples_replayed=120,
                ready_windows=2,
                created_windows=2,
                duplicate_windows=0,
                alert_windows=1,
                no_data_windows=0,
                failures=0,
                recent_inferences=(
                    RecentReplayInference(
                        mission_index=271,
                        window_index=1,
                        model_version="fendt314-hybrid-v2.0.1",
                        hybrid_alert=True,
                    ),
                ),
                error_code=None,
            )

    app = create_app(
        usage_model=object(),
        engine=create_engine("sqlite://"),
        replay_progress=Reader(),
    )
    app.dependency_overrides[current_user] = lambda: INSURER
    with TestClient(app) as client:
        response = client.get("/v1/demo/replay-progress")

    assert response.status_code == 200
    assert response.json() == {
        "evidence_role": "operational_output_only",
        "status": "running",
        "tractor_id": "tractor-id",
        "telemetry_import_id": "import-id",
        "dataset_split": "validation",
        "source_doi": "10.5281/zenodo.14619787",
        "source_license": "CC-BY-4.0",
        "semantic_sha256": "a" * 64,
        "total_samples": 152_561,
        "samples_replayed": 120,
        "ready_windows": 2,
        "created_windows": 2,
        "duplicate_windows": 0,
        "alert_windows": 1,
        "no_data_windows": 0,
        "failures": 0,
        "recent_inferences": [
            {
                "mission_index": 271,
                "window_index": 1,
                "model_version": "fendt314-hybrid-v2.0.1",
                "hybrid_alert": True,
            }
        ],
        "error_code": None,
    }


def test_startup_does_not_create_an_engine_when_the_model_cannot_load(monkeypatch) -> None:
    from tractor_usage.api import app as app_module

    engine_created = False

    def fail_model_load(_):
        raise ModelUnavailableError("missing bundle")

    def track_engine_creation(_):
        nonlocal engine_created
        engine_created = True
        return create_engine("sqlite://")

    monkeypatch.setattr(app_module.FrozenBundleUsageModel, "load", fail_model_load)
    monkeypatch.setattr(app_module, "create_database_engine", track_engine_creation)
    test_app = create_app(
        settings=Settings(database_url="sqlite://", model_dir=Path("missing"))
    )

    with pytest.raises(ModelUnavailableError, match="missing bundle"):
        with TestClient(test_app):
            pass

    assert engine_created is False


class _FleetRepository:
    @contextmanager
    def transaction(self):
        yield

    def create_fleet(self, request):
        created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        fleet = Fleet(id="fleet-1", name=request.name, created_at_utc=created_at)
        tractors = tuple(
            Tractor(
                id=f"tractor-{index}",
                fleet_id=fleet.id,
                external_id=tractor.external_id,
                display_name=tractor.display_name,
                model_name="Fendt 314",
                created_at_utc=created_at,
            )
            for index, tractor in enumerate(request.tractors, start=1)
        )
        return FleetRegistration(fleet=fleet, tractors=tractors)


def test_registration_endpoint_projects_created_resources(monkeypatch) -> None:
    from tractor_usage.api import routes

    app = create_app(usage_model=object(), engine=create_engine("sqlite://"))
    app.dependency_overrides[current_user] = lambda: INSURER
    app.dependency_overrides[routes.request_session] = lambda: object()
    monkeypatch.setattr(routes, "PostgresInspectionRepository", lambda _: _FleetRepository())

    with TestClient(app) as client:
        response = client.post(
            "/v1/fleets",
            json={
                "name": "Fazenda Norte",
                "tractors": [{"external_id": "F314-01", "display_name": "Trator 1"}],
            },
        )

    assert response.status_code == 201
    assert response.json() == {
        "evidence_role": "operational_output_only",
        "fleet": {
            "id": "fleet-1",
            "name": "Fazenda Norte",
            "created_at_utc": "2026-01-01T00:00:00+00:00",
        },
        "tractors": [
            {
                "id": "tractor-1",
                "fleet_id": "fleet-1",
                "external_id": "F314-01",
                "display_name": "Trator 1",
                "model_name": "Fendt 314",
                "created_at_utc": "2026-01-01T00:00:00+00:00",
            }
        ],
    }


@pytest.mark.parametrize("endpoint", ("imports/preview", "imports"))
@pytest.mark.parametrize("oversized_field", ("observed_at_utc", "1700.0"))
def test_csv_intake_rejects_oversized_header_or_value_as_validation_error(
    monkeypatch, endpoint: str, oversized_field: str
) -> None:
    from tractor_usage.api import intake
    from tractor_usage.infrastructure.simulated_scenarios import scenario_csv

    app = create_app(usage_model=object(), engine=create_engine("sqlite://"))
    app.dependency_overrides[current_user] = lambda: INSURER
    monkeypatch.setattr(intake, "validate_intake_tractor", lambda *args: None)
    csv_text = "\n".join(scenario_csv("aurora-regular").splitlines()[:61]) + "\n"
    csv_text = csv_text.replace(oversized_field, "1" * 140_000, 1)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            f"/v1/tractors/00000000-0000-0000-0000-000000000001/{endpoint}",
            json={
                "file_name": "telemetry.csv",
                "source_kind": "simulated_csv",
                "csv_text": csv_text,
            },
        )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Não foi possível ler o CSV. Verifique a formatação e o tamanho dos campos."
    }
