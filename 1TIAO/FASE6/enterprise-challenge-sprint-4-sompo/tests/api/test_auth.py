from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import Depends
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from tractor_usage.api.app import create_app
from tractor_usage.api.auth import SESSION_COOKIE, require_ingest_token
from tractor_usage.application.auth import hash_password, verify_password
from tractor_usage.infrastructure.auth_repository import AuthRepository
from tractor_usage.infrastructure.models import FleetRecord, UserRecord, UserSessionRecord


def _engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    for record in (FleetRecord, UserRecord, UserSessionRecord):
        record.__table__.create(engine)
    return engine


def test_password_hash_is_salted_and_rejects_invalid_passwords() -> None:
    first = hash_password("a-long-password-for-a-user")
    second = hash_password("a-long-password-for-a-user")

    assert first != second
    assert "a-long-password-for-a-user" not in first
    assert verify_password("a-long-password-for-a-user", first)
    assert not verify_password("different-password", first)
    assert not verify_password("anything", "invalid-hash")
    assert not verify_password("anything", "scrypt:16384:8:1:!:!")


def test_login_me_logout_and_session_expiry() -> None:
    engine = _engine()
    try:
        with Session(engine) as session:
            principal = AuthRepository(session).create_user(
                worker_id="000123",
                password="correct-horse-battery-staple",
                role="INSURER",
            )
        assert principal.worker_id == "000123"

        app = create_app(usage_model=object(), engine=engine)
        with TestClient(app) as client:
            invalid = client.post(
                "/v1/auth/login",
                json={"worker_id": principal.worker_id, "password": "wrong-password"},
            )
            assert invalid.status_code == 401
            assert client.get("/v1/auth/me").status_code == 401

            login = client.post(
                "/v1/auth/login",
                json={
                    "worker_id": "000123",
                    "password": "correct-horse-battery-staple",
                },
            )
            assert login.status_code == 200
            assert login.json() == {
                "id": principal.id,
                "worker_id": principal.worker_id,
                "role": "INSURER",
                "fleet_id": None,
            }
            cookie = login.headers["set-cookie"].lower()
            assert "httponly" in cookie and "samesite=lax" in cookie and "path=/" in cookie
            assert client.get("/v1/auth/me").json() == login.json()
            token = client.cookies.get(SESSION_COOKIE)
            assert token is not None
            with Session(engine) as session:
                stored = session.scalar(select(UserSessionRecord))
                assert stored is not None and stored.token_digest != token

            cross_site = client.post(
                "/v1/auth/logout", headers={"Origin": "https://unrelated.example"}
            )
            assert cross_site.status_code == 403
            assert client.get("/v1/auth/me").status_code == 200

            with Session(engine) as session:
                session.execute(
                    update(UserSessionRecord).values(
                        expires_at_utc=datetime.now(timezone.utc) - timedelta(seconds=1)
                    )
                )
                session.commit()
            assert client.get("/v1/auth/me").status_code == 401

            login = client.post(
                "/v1/auth/login",
                json={"worker_id": principal.worker_id, "password": "correct-horse-battery-staple"},
            )
            assert login.status_code == 200
            assert client.post("/v1/auth/logout").status_code == 204
            assert client.get("/v1/auth/me").status_code == 401
    finally:
        engine.dispose()


def test_fleet_manager_scope_and_role_change_revoke_sessions() -> None:
    engine = _engine()
    try:
        with Session(engine) as session:
            fleet = FleetRecord(name="A fleet")
            session.add(fleet)
            session.commit()
            fleet_id = str(fleet.id)
            repository = AuthRepository(session)
            principal = repository.create_user(
                worker_id="000007",
                password="manager-long-password",
                role="FLEET_MANAGER",
                fleet_id=fleet_id,
            )
            assert principal.fleet_id == fleet_id
            token = repository.create_session(principal.id)
            assert repository.principal_for_session(token) == principal
            changed = repository.set_access(principal.id, role="INSPECTOR")
            assert changed.role == "INSPECTOR" and changed.fleet_id is None
            assert repository.principal_for_session(token) is None
    finally:
        engine.dispose()


def test_worker_id_requires_ascii_digits_without_losing_leading_zeros() -> None:
    engine = _engine()
    try:
        with Session(engine) as session:
            repository = AuthRepository(session)
            with pytest.raises(ValueError, match="ASCII digits"):
                repository.create_user(
                    worker_id="12A3", password="a-valid-password", role="INSURER"
                )
            with pytest.raises(ValueError, match="ASCII digits"):
                repository.create_user(
                    worker_id="１２３", password="a-valid-password", role="INSURER"
                )
            principal = repository.create_user(
                worker_id="0001", password="a-valid-password", role="INSURER"
            )
            assert principal.worker_id == "0001"
            assert repository.user_by_worker_id("0001") == principal
            assert repository.user_by_worker_id("1") is None

        with TestClient(create_app(usage_model=object(), engine=engine)) as client:
            assert client.post(
                "/v1/auth/login", json={"worker_id": 1, "password": "a-valid-password"}
            ).status_code == 422
            assert client.post(
                "/v1/auth/login", json={"worker_id": "１２３", "password": "a-valid-password"}
            ).status_code == 422
    finally:
        engine.dispose()


def test_cli_repository_preserves_a_last_active_administrator() -> None:
    engine = _engine()
    try:
        with Session(engine) as session:
            repository = AuthRepository(session)
            administrator = repository.create_user(
                worker_id="000999", password="administrator-password", role="ADMIN"
            )
            with pytest.raises(ValueError, match="active administrator"):
                repository.set_access(administrator.id, role="INSURER")
            session.rollback()
            with pytest.raises(ValueError, match="active administrator"):
                repository.disable_user(administrator.id)
            session.rollback()
            second = repository.create_user(
                worker_id="000998", password="second-admin-password", role="ADMIN"
            )
            repository.set_access(second.id, role="INSURER")
            assert repository.user_by_worker_id("000999").role == "ADMIN"
    finally:
        engine.dispose()


def test_ingest_requires_a_separate_service_token() -> None:
    engine = _engine()
    try:
        app = create_app(usage_model=object(), engine=engine, ingest_token="a-service-secret")

        @app.post("/test-ingest", dependencies=[Depends(require_ingest_token)])
        def test_ingest():
            return {"accepted": True}

        with TestClient(app) as client:
            assert client.post("/test-ingest").status_code == 401
            assert client.post("/test-ingest", headers={"X-Ingest-Token": "wrong"}).status_code == 401
            assert client.post(
                "/test-ingest", headers={"X-Ingest-Token": "a-service-secret"}
            ).json() == {"accepted": True}
    finally:
        engine.dispose()
