"""PostgreSQL accounts and revocable, opaque browser sessions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from secrets import token_urlsafe
from typing import cast
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tractor_usage.application.auth import (
    Principal,
    Role,
    hash_password,
    validate_worker_id,
    verify_password,
)
from tractor_usage.infrastructure.models import UserRecord, UserSessionRecord


SESSION_TTL = timedelta(hours=8)
_DUMMY_PASSWORD_HASH = hash_password("invalid-account-password")


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _digest(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def _principal(record: UserRecord) -> Principal:
    return Principal(
        id=str(record.id),
        worker_id=record.worker_id,
        role=cast(Role, record.role),
        fleet_id=str(record.fleet_id) if record.fleet_id is not None else None,
    )


def _validate_role_scope(role: Role, fleet_id: str | None) -> UUID | None:
    if role not in ("ADMIN", "INSURER", "INSPECTOR", "FLEET_MANAGER"):
        raise ValueError("unsupported role")
    if (role == "FLEET_MANAGER") != (fleet_id is not None):
        raise ValueError("fleet managers require a fleet; other roles are global")
    return UUID(fleet_id) if fleet_id is not None else None


class AuthRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_active_inspectors(self) -> tuple[Principal, ...]:
        records = self._session.scalars(
            select(UserRecord)
            .where(UserRecord.role == "INSPECTOR", UserRecord.active.is_(True))
            .order_by(UserRecord.worker_id)
        )
        return tuple(_principal(record) for record in records)

    def is_active_inspector(self, worker_id: str) -> bool:
        return self._session.scalar(
            select(UserRecord.id).where(
                UserRecord.worker_id == worker_id,
                UserRecord.role == "INSPECTOR",
                UserRecord.active.is_(True),
            )
        ) is not None

    def create_user(
        self,
        *,
        worker_id: str,
        password: str,
        role: Role,
        fleet_id: str | None = None,
    ) -> Principal:
        validated = validate_worker_id(worker_id)
        fleet_uuid = _validate_role_scope(role, fleet_id)
        record = UserRecord(
            worker_id=validated,
            password_hash=hash_password(password),
            role=role,
            fleet_id=fleet_uuid,
            active=True,
        )
        try:
            self._session.add(record)
            self._session.commit()
        except IntegrityError as error:
            self._session.rollback()
            raise ValueError("account or fleet conflicts with existing data") from error
        return _principal(record)

    def user_by_worker_id(self, worker_id: str) -> Principal | None:
        record = self._session.scalar(
            select(UserRecord).where(UserRecord.worker_id == validate_worker_id(worker_id))
        )
        return _principal(record) if record is not None else None

    def authenticate(self, worker_id: str, password: str) -> Principal | None:
        try:
            validated = validate_worker_id(worker_id)
        except ValueError:
            validated = ""
        record = self._session.scalar(
            select(UserRecord).where(UserRecord.worker_id == validated)
        )
        valid_password = verify_password(
            password,
            record.password_hash if record is not None else _DUMMY_PASSWORD_HASH,
        )
        if record is None or not record.active or not valid_password:
            return None
        return _principal(record)

    def create_session(self, user_id: str) -> str:
        token = token_urlsafe(32)
        now = _now_utc()
        self._session.add(
            UserSessionRecord(
                token_digest=_digest(token),
                user_id=UUID(user_id),
                created_at_utc=now,
                expires_at_utc=now + SESSION_TTL,
            )
        )
        self._session.commit()
        return token

    def principal_for_session(self, token: str) -> Principal | None:
        record = self._session.scalar(
            select(UserRecord)
            .join(UserSessionRecord, UserSessionRecord.user_id == UserRecord.id)
            .where(
                UserSessionRecord.token_digest == _digest(token),
                UserSessionRecord.expires_at_utc > _now_utc(),
                UserSessionRecord.revoked_at_utc.is_(None),
                UserRecord.active.is_(True),
            )
        )
        return _principal(record) if record is not None else None

    def revoke_session(self, token: str) -> None:
        self._session.execute(
            update(UserSessionRecord)
            .where(
                UserSessionRecord.token_digest == _digest(token),
                UserSessionRecord.revoked_at_utc.is_(None),
            )
            .values(revoked_at_utc=_now_utc())
        )
        self._session.commit()

    def change_password(self, user_id: str, password: str) -> None:
        password_hash = hash_password(password)
        result = self._session.execute(
            update(UserRecord)
            .where(UserRecord.id == UUID(user_id))
            .values(password_hash=password_hash)
        )
        if result.rowcount != 1:
            self._session.rollback()
            raise ValueError("user not found")
        self._session.execute(
            update(UserSessionRecord)
            .where(
                UserSessionRecord.user_id == UUID(user_id),
                UserSessionRecord.revoked_at_utc.is_(None),
            )
            .values(revoked_at_utc=_now_utc())
        )
        self._session.commit()

    def set_access(self, user_id: str, *, role: Role, fleet_id: str | None = None) -> Principal:
        fleet_uuid = _validate_role_scope(role, fleet_id)
        active_admins = self._active_admins_for_update()
        record = self._session.get(UserRecord, UUID(user_id))
        if record is None:
            raise ValueError("user not found")
        if record.role == "ADMIN" and record.active and role != "ADMIN" and len(active_admins) <= 1:
            raise ValueError("at least one active administrator is required")
        record.role = role
        record.fleet_id = fleet_uuid
        self._revoke_user_sessions(user_id)
        try:
            self._session.commit()
        except IntegrityError as error:
            self._session.rollback()
            raise ValueError("fleet conflicts with existing data") from error
        return _principal(record)

    def disable_user(self, user_id: str) -> None:
        active_admins = self._active_admins_for_update()
        record = self._session.get(UserRecord, UUID(user_id))
        if record is None:
            raise ValueError("user not found")
        if record.role == "ADMIN" and record.active and len(active_admins) <= 1:
            raise ValueError("at least one active administrator is required")
        record.active = False
        self._revoke_user_sessions(user_id)
        self._session.commit()

    def enable_user(self, user_id: str) -> None:
        record = self._session.get(UserRecord, UUID(user_id))
        if record is None:
            raise ValueError("user not found")
        record.active = True
        self._session.commit()

    def _revoke_user_sessions(self, user_id: str) -> None:
        self._session.execute(
            update(UserSessionRecord)
            .where(
                UserSessionRecord.user_id == UUID(user_id),
                UserSessionRecord.revoked_at_utc.is_(None),
            )
            .values(revoked_at_utc=_now_utc())
        )

    def _active_admins_for_update(self) -> tuple[UserRecord, ...]:
        return tuple(
            self._session.scalars(
                select(UserRecord)
                .where(UserRecord.role == "ADMIN", UserRecord.active.is_(True))
                .order_by(UserRecord.id)
                .with_for_update()
            )
        )
