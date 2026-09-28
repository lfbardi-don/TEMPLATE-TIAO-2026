"""One HTTP journey proves actual frozen inference, atomic intake, and access."""
import os
from pathlib import Path
from uuid import UUID, uuid4

import pytest

DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
if not DATABASE_URL:
    pytest.skip("TEST_DATABASE_URL is not configured", allow_module_level=True)

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.orm import Session

from tractor_usage.api.app import create_app
from tractor_usage.api.auth import current_user
from tractor_usage.application.auth import Principal
from tractor_usage.application.contracts import ModelUnavailableError
from tractor_usage.infrastructure.database import Settings
from tractor_usage.infrastructure.models import Base, FleetRecord, TractorRecord, TelemetryImportRecord, TelemetryMissionRecord, TelemetrySampleRecord, ScoredWindowRecord
from tractor_usage.infrastructure.simulated_scenarios import scenario_csv


def test_operational_csv_http_journey():
    engine = create_engine(DATABASE_URL)
    Base.metadata.create_all(engine)
    fleet_id = None
    try:
        settings = Settings(DATABASE_URL, Path(__file__).resolve().parents[2] / "models/fendt314-hybrid-v2.0.1")
        app = create_app(settings=settings, engine=engine)
        principal = Principal(id=str(uuid4()), worker_id="9101", role="INSURER", fleet_id=None)
        app.dependency_overrides[current_user] = lambda: principal
        with TestClient(app) as client:
            created = client.post("/v1/fleets", json={"name": f"intake-{uuid4()}", "tractors": [{"external_id": "sim-01"}]})
            assert created.status_code == 201
            fleet_id = created.json()["fleet"]["id"]
            tractor_id = created.json()["tractors"][0]["id"]
            empty = next(f for f in client.get("/v1/catalog").json()["fleets"] if f["id"] == fleet_id)["tractors"][0]
            assert empty["window_count"] == 0 and empty["source_kind"] is None
            assert client.post(f"/v1/fleets/{fleet_id}/tractors", json={"external_id": "sim-02"}).status_code == 201
            raw = scenario_csv("aurora-carga").splitlines()
            # Three minutes retain a full alert interval and its raw evidence.
            payload = {"file_name": "synthetic.csv", "source_kind": "simulated_csv", "csv_text": "\n".join([raw[0], *raw[601:781]]) + "\n"}
            preview = client.post(f"/v1/tractors/{tractor_id}/imports/preview", json=payload)
            assert preview.status_code == 200 and preview.json()["ready_window_count"] == 3
            imported = client.post(f"/v1/tractors/{tractor_id}/imports", json=payload)
            assert imported.status_code == 201, imported.text
            data = imported.json()
            assert data["window_count"] == 3 and data["alert_count"] > 0
            assert data["source_kind"] == "simulated_csv" and data["imported_by_worker_id"] == "9101"
            duplicate = client.post(f"/v1/tractors/{tractor_id}/imports", json={**payload, "file_name": "renamed.csv", "csv_text": payload["csv_text"].replace("\n", "\r\n")})
            assert duplicate.status_code == 200 and duplicate.json()["duplicate"]
            assert duplicate.json()["id"] == data["id"]
            assert client.post(f"/v1/tractors/{tractor_id}/imports", json={**payload, "source_kind": "operational_csv"}).status_code == 409
            assert client.post(f"/v1/tractors/{tractor_id}/imports", json={**payload, "csv_text": payload["csv_text"].replace(",83,", ",82,", 1)}).status_code == 409
            chart = client.get(f"/v1/tractors/{tractor_id}/telemetry-chart?limit=30").json()
            assert chart["total_samples"] == 180 and 1 <= len(chart["samples"]) <= 30
            assert chart["periods"][0]["import_id"] == data["id"]
            assert client.get(f"/v1/tractors/{tractor_id}/imports").json()["imports"][0]["id"] == data["id"]
            # Episode detail reconstructs persisted samples and checks rule seconds.
            overview = client.get(f"/v1/tractors/{tractor_id}/overview")
            assert overview.status_code == 200, overview.text
            episode_id = overview.json()["episodes_last_30_days"][0]["id"]
            assert client.get(f"/v1/tractors/{tractor_id}/episodes/{episode_id}").status_code == 200
            class UnavailableModel:
                model_version = "fendt314-hybrid-v2.0.1"

                def score(self, *_):
                    raise ModelUnavailableError("test inference failure")

            app.state.usage_model = UnavailableModel()
            failed = client.post(f"/v1/tractors/{tractor_id}/imports", json={**payload, "csv_text": payload["csv_text"].replace("2026-09-01", "2026-09-02")})
            assert failed.status_code == 500
            assert len(client.get(f"/v1/tractors/{tractor_id}/imports").json()["imports"]) == 1
            principal = Principal(id=principal.id, worker_id="9100", role="ADMIN", fleet_id=None)
            assert client.post(f"/v1/tractors/{tractor_id}/imports", json=payload).status_code == 403
            assert client.get(f"/v1/tractors/{tractor_id}/imports").status_code == 200
            principal = Principal(id=principal.id, worker_id="9102", role="FLEET_MANAGER", fleet_id=str(uuid4()))
            assert client.get("/v1/catalog").json() == {"fleets": []}
            assert client.get(f"/v1/tractors/{tractor_id}/telemetry-chart").status_code == 404
        with Session(engine) as session:
            assert session.scalar(select(func.count()).select_from(TelemetryImportRecord).where(TelemetryImportRecord.tractor_id == UUID(tractor_id))) == 1
            assert session.scalar(select(func.count()).select_from(ScoredWindowRecord).where(ScoredWindowRecord.tractor_id == UUID(tractor_id))) == 3
    finally:
        if fleet_id:
            with Session(engine) as session:
                tractor_ids = select(TractorRecord.id).where(TractorRecord.fleet_id == UUID(fleet_id))
                import_ids = select(TelemetryImportRecord.id).where(TelemetryImportRecord.tractor_id.in_(tractor_ids))
                session.execute(delete(ScoredWindowRecord).where(ScoredWindowRecord.tractor_id.in_(tractor_ids)))
                session.execute(delete(TelemetrySampleRecord).where(TelemetrySampleRecord.import_id.in_(import_ids)))
                session.execute(delete(TelemetryMissionRecord).where(TelemetryMissionRecord.import_id.in_(import_ids)))
                session.execute(delete(TelemetryImportRecord).where(TelemetryImportRecord.tractor_id.in_(tractor_ids)))
                session.execute(delete(TractorRecord).where(TractorRecord.fleet_id == UUID(fleet_id)))
                session.execute(delete(FleetRecord).where(FleetRecord.id == UUID(fleet_id)))
                session.commit()
        engine.dispose()
