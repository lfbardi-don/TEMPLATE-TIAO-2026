"""Persisted administrator permissions, account changes, and action history."""

from __future__ import annotations

import os
from uuid import UUID, uuid4

import pytest

DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
if not DATABASE_URL:
    pytest.skip("TEST_DATABASE_URL is not configured", allow_module_level=True)

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import Session

from tractor_usage.api.app import create_app
from tractor_usage.infrastructure.admin_repository import AdminAccountRepository
from tractor_usage.infrastructure.auth_repository import AuthRepository
from tractor_usage.infrastructure.models import (
    AdminUserEventRecord,
    Base,
    FleetRecord,
    TractorRecord,
    UserRecord,
    UserSessionRecord,
)


def _worker_id() -> str:
    return str(10**15 + uuid4().int % 10**15)


def test_admin_api_manages_accounts_and_records_atomic_history(monkeypatch) -> None:
    engine = create_engine(DATABASE_URL)
    admin_worker, insurer_worker, manager_worker, other_admin_worker = (
        _worker_id() for _ in range(4)
    )
    created_user_ids: list[UUID] = []
    fleet_id: UUID | None = None
    tractor_id: UUID | None = None
    tractor_external_id = f"unscored-{uuid4()}"
    try:
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            fleet = FleetRecord(name=f"admin-test-{uuid4()}")
            session.add(fleet)
            session.flush()
            tractor = TractorRecord(
                fleet_id=fleet.id,
                external_id=tractor_external_id,
                display_name="Sem telemetria",
            )
            session.add(tractor)
            session.commit()
            fleet_id = fleet.id
            tractor_id = tractor.id
            auth = AuthRepository(session)
            administrator = auth.create_user(
                worker_id=admin_worker,
                password="initial-admin-password",
                role="ADMIN",
            )
            insurer = auth.create_user(
                worker_id=insurer_worker,
                password="initial-insurer-password",
                role="INSURER",
            )
            created_user_ids.extend((UUID(administrator.id), UUID(insurer.id)))

        app = create_app(usage_model=object(), engine=engine)
        with TestClient(app) as anonymous:
            assert anonymous.get("/v1/admin/users").status_code == 401
            assert anonymous.get("/v1/admin/catalog").status_code == 401
            assert anonymous.get("/v1/admin/user-events").status_code == 401

        with TestClient(app) as non_admin:
            assert non_admin.post(
                "/v1/auth/login",
                json={"worker_id": insurer_worker, "password": "initial-insurer-password"},
            ).status_code == 200
            assert non_admin.get("/v1/admin/users").status_code == 403
            assert non_admin.get("/v1/admin/catalog").status_code == 403
            assert non_admin.get("/v1/admin/user-events").status_code == 403
            assert non_admin.post(
                "/v1/admin/users",
                json={"worker_id": _worker_id(), "role": "INSPECTOR", "fleet_id": None},
            ).status_code == 403

        with TestClient(app) as admin:
            login = admin.post(
                "/v1/auth/login",
                json={"worker_id": admin_worker, "password": "initial-admin-password"},
            )
            assert login.status_code == 200
            assert login.json()["role"] == "ADMIN"
            users = admin.get("/v1/admin/users")
            assert users.status_code == 200
            assert users.headers["cache-control"] == "no-store"
            assert {admin_worker, insurer_worker} <= {
                user["worker_id"] for user in users.json()["users"]
            }
            assert "password_hash" not in users.text
            catalog = admin.get("/v1/admin/catalog")
            assert catalog.status_code == 200
            demo_fleet = next(
                fleet for fleet in catalog.json()["fleets"] if fleet["id"] == str(fleet_id)
            )
            assert demo_fleet["tractors"] == [{
                "id": str(tractor_id),
                "external_id": tractor_external_id,
                "display_name": "Sem telemetria",
                "model_name": "Fendt 314",
            }]

            assert admin.post(
                "/v1/admin/users",
                json={"worker_id": _worker_id(), "role": "FLEET_MANAGER", "fleet_id": None},
            ).status_code == 422
            assert admin.post(
                "/v1/admin/users",
                json={"worker_id": _worker_id(), "role": "ADMIN", "fleet_id": str(fleet_id)},
            ).status_code == 422

            created = admin.post(
                "/v1/admin/users",
                json={
                    "worker_id": manager_worker,
                    "role": "FLEET_MANAGER",
                    "fleet_id": str(fleet_id),
                },
            )
            assert created.status_code == 201, created.text
            assert created.headers["cache-control"] == "no-store"
            manager = created.json()["user"]
            manager_password = created.json()["temporary_password"]
            created_user_ids.append(UUID(manager["id"]))
            assert manager["active"] is True and manager["fleet_id"] == str(fleet_id)
            assert len(manager_password) >= 12
            assert admin.post(
                "/v1/admin/users",
                json={"worker_id": manager_worker, "role": "INSPECTOR", "fleet_id": None},
            ).status_code == 409

            events = admin.get("/v1/admin/user-events").json()["events"]
            created_event = next(event for event in events if event["target_user_id"] == manager["id"])
            assert created_event["action"] == "CREATE"
            assert created_event["actor_user_id"] == administrator.id
            assert created_event["actor_worker_id"] == admin_worker
            assert created_event["details"] == {
                "role": "FLEET_MANAGER", "fleet_id": str(fleet_id), "active": True
            }
            assert manager_password not in str(events)

            with TestClient(app) as manager_client:
                assert manager_client.post(
                    "/v1/auth/login",
                    json={"worker_id": manager_worker, "password": manager_password},
                ).status_code == 200
                assert manager_client.get("/v1/auth/me").status_code == 200
                updated = admin.patch(
                    f"/v1/admin/users/{manager['id']}",
                    json={"role": "INSPECTOR", "fleet_id": None, "active": True},
                )
                assert updated.status_code == 200, updated.text
                assert updated.json()["user"]["role"] == "INSPECTOR"
                assert manager_client.get("/v1/auth/me").status_code == 401

            def fail_event(*_args, **_kwargs):
                raise RuntimeError("simulated account event failure")

            with monkeypatch.context() as patch:
                patch.setattr(AdminAccountRepository, "_append_event", fail_event)
                with pytest.raises(RuntimeError, match="simulated account event failure"):
                    admin.patch(
                        f"/v1/admin/users/{manager['id']}",
                        json={"role": "FLEET_MANAGER", "fleet_id": str(fleet_id), "active": True},
                    )
            assert next(
                user for user in admin.get("/v1/admin/users").json()["users"]
                if user["id"] == manager["id"]
            )["role"] == "INSPECTOR"

            reset = admin.post(f"/v1/admin/users/{manager['id']}/reset-password")
            assert reset.status_code == 200
            next_password = reset.json()["temporary_password"]
            assert next_password != manager_password
            assert admin.patch(
                f"/v1/admin/users/{administrator.id}",
                json={"role": "INSURER", "fleet_id": None, "active": True},
            ).status_code == 409
            assert admin.patch(
                f"/v1/admin/users/{administrator.id}",
                json={"role": "ADMIN", "fleet_id": None, "active": False},
            ).status_code == 409

            second_admin = admin.post(
                "/v1/admin/users",
                json={"worker_id": other_admin_worker, "role": "ADMIN", "fleet_id": None},
            )
            assert second_admin.status_code == 201
            created_user_ids.append(UUID(second_admin.json()["user"]["id"]))
            assert admin.patch(
                f"/v1/admin/users/{second_admin.json()['user']['id']}",
                json={"role": "INSURER", "fleet_id": None, "active": True},
            ).status_code == 200

            events = admin.get("/v1/admin/user-events").json()["events"]
            manager_actions = [
                event["action"] for event in reversed(events)
                if event["target_user_id"] == manager["id"]
            ]
            assert manager_actions == ["CREATE", "UPDATE", "RESET_PASSWORD"]
            assert manager_password not in str(events)
            assert next_password not in str(events)
            assert events[0]["occurred_at_utc"].endswith("+00:00")

            with Session(engine) as session:
                stored_manager = session.get(UserRecord, UUID(manager["id"]))
                assert stored_manager is not None
                assert manager_password not in stored_manager.password_hash
                assert next_password not in stored_manager.password_hash
                assert AuthRepository(session).authenticate(manager_worker, next_password)
    finally:
        if created_user_ids or fleet_id is not None:
            with Session(engine) as session, session.begin():
                session.execute(
                    delete(AdminUserEventRecord).where(
                        AdminUserEventRecord.actor_user_id.in_(created_user_ids)
                    )
                )
                session.execute(
                    delete(UserSessionRecord).where(
                        UserSessionRecord.user_id.in_(created_user_ids)
                    )
                )
                session.execute(delete(UserRecord).where(UserRecord.id.in_(created_user_ids)))
                if fleet_id is not None:
                    if tractor_id is not None:
                        session.execute(delete(TractorRecord).where(TractorRecord.id == tractor_id))
                    session.execute(delete(FleetRecord).where(FleetRecord.id == fleet_id))
        engine.dispose()
