"""Transactional account management and its action history."""

from __future__ import annotations

from datetime import datetime, timezone
from secrets import token_urlsafe
from typing import Literal, cast
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tractor_usage.application.auth import (
    AdminAccount,
    AdminUserEvent,
    Principal,
    Role,
    hash_password,
    validate_worker_id,
)
from tractor_usage.application.contracts import ConflictError, NotFoundError
from tractor_usage.infrastructure.auth_repository import _validate_role_scope
from tractor_usage.infrastructure.models import (
    AdminUserEventRecord,
    FleetRecord,
    TractorRecord,
    UserRecord,
    UserSessionRecord,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _account(record: UserRecord) -> AdminAccount:
    return AdminAccount(
        id=str(record.id),
        worker_id=record.worker_id,
        role=cast(Role, record.role),
        fleet_id=str(record.fleet_id) if record.fleet_id is not None else None,
        active=record.active,
        created_at_utc=record.created_at_utc.astimezone(timezone.utc),
    )


def _event(record: AdminUserEventRecord) -> AdminUserEvent:
    return AdminUserEvent(
        id=str(record.id),
        target_user_id=str(record.target_user_id),
        target_worker_id=record.target_worker_id,
        actor_user_id=str(record.actor_user_id),
        actor_worker_id=record.actor_worker_id,
        action=cast(Literal["CREATE", "UPDATE", "RESET_PASSWORD"], record.action),
        occurred_at_utc=record.occurred_at_utc.astimezone(timezone.utc),
        details=dict(record.details),
    )


class AdminAccountRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_users(self) -> tuple[AdminAccount, ...]:
        return tuple(
            _account(record)
            for record in self._session.scalars(
                select(UserRecord).order_by(UserRecord.worker_id, UserRecord.id)
            )
        )

    def list_events(self) -> tuple[AdminUserEvent, ...]:
        return tuple(
            _event(record)
            for record in self._session.scalars(
                select(AdminUserEventRecord).order_by(
                    AdminUserEventRecord.occurred_at_utc.desc(),
                    AdminUserEventRecord.id.desc(),
                )
            )
        )

    def list_catalog(self) -> tuple[dict[str, object], ...]:
        fleets: dict[str, dict[str, object]] = {}
        rows = self._session.execute(
            select(FleetRecord, TractorRecord)
            .outerjoin(TractorRecord, TractorRecord.fleet_id == FleetRecord.id)
            .order_by(
                FleetRecord.name, FleetRecord.id,
                TractorRecord.external_id, TractorRecord.id,
            )
        )
        for fleet, tractor in rows:
            key = str(fleet.id)
            if key not in fleets:
                fleets[key] = {"id": key, "name": fleet.name, "tractors": []}
            if tractor is not None:
                fleets[key]["tractors"].append(
                    {
                        "id": str(tractor.id),
                        "external_id": tractor.external_id,
                        "display_name": tractor.display_name,
                        "model_name": tractor.model_name,
                    }
                )
        return tuple(fleets.values())

    def create_user(
        self,
        *,
        actor: Principal,
        worker_id: str,
        role: Role,
        fleet_id: str | None,
    ) -> tuple[AdminAccount, str]:
        validated_worker_id = validate_worker_id(worker_id)
        fleet_uuid = _validate_role_scope(role, fleet_id)
        temporary_password = token_urlsafe(24)
        password_hash = hash_password(temporary_password)
        now = _utc_now()
        try:
            with self._session.begin():
                self._require_active_admin(actor)
                record = UserRecord(
                    id=uuid4(),
                    worker_id=validated_worker_id,
                    password_hash=password_hash,
                    role=role,
                    fleet_id=fleet_uuid,
                    active=True,
                    created_at_utc=now,
                )
                self._session.add(record)
                self._session.flush()
                self._append_event(
                    actor, record, "CREATE", now,
                    {"role": role, "fleet_id": fleet_id, "active": True},
                )
                result = _account(record)
        except IntegrityError as error:
            raise ConflictError("account or fleet conflicts with existing data") from error
        return result, temporary_password

    def update_user(
        self,
        *,
        actor: Principal,
        user_id: str,
        role: Role,
        fleet_id: str | None,
        active: bool,
    ) -> AdminAccount:
        fleet_uuid = _validate_role_scope(role, fleet_id)
        now = _utc_now()
        try:
            with self._session.begin():
                active_admins = tuple(
                    self._session.scalars(
                        select(UserRecord)
                        .where(UserRecord.role == "ADMIN", UserRecord.active.is_(True))
                        .order_by(UserRecord.id)
                        .with_for_update()
                    )
                )
                if not any(record.id == UUID(actor.id) for record in active_admins):
                    raise ConflictError("administrator access changed; sign in again")
                record = self._session.get(UserRecord, UUID(user_id), with_for_update=True)
                if record is None:
                    raise NotFoundError("user not found")
                if record.id == UUID(actor.id) and (role != "ADMIN" or not active):
                    raise ConflictError("administrator cannot demote or disable own account")
                if (
                    record.role == "ADMIN"
                    and record.active
                    and (role != "ADMIN" or not active)
                    and len(active_admins) <= 1
                ):
                    raise ConflictError("at least one active administrator is required")
                changes = _account_changes(record, role, fleet_uuid, active)
                record.role = role
                record.fleet_id = fleet_uuid
                record.active = active
                if changes:
                    self._revoke_sessions(record.id, now)
                self._append_event(actor, record, "UPDATE", now, {"changes": changes})
                self._session.flush()
                result = _account(record)
        except IntegrityError as error:
            raise ConflictError("account or fleet conflicts with existing data") from error
        return result

    def reset_password(self, *, actor: Principal, user_id: str) -> str:
        temporary_password = token_urlsafe(24)
        password_hash = hash_password(temporary_password)
        now = _utc_now()
        with self._session.begin():
            self._require_active_admin(actor)
            record = self._session.get(UserRecord, UUID(user_id), with_for_update=True)
            if record is None:
                raise NotFoundError("user not found")
            record.password_hash = password_hash
            self._revoke_sessions(record.id, now)
            self._append_event(actor, record, "RESET_PASSWORD", now, {})
            self._session.flush()
        return temporary_password

    def _require_active_admin(self, actor: Principal) -> None:
        record = self._session.get(UserRecord, UUID(actor.id), with_for_update=True)
        if record is None or record.role != "ADMIN" or not record.active:
            raise ConflictError("administrator access changed; sign in again")

    def _revoke_sessions(self, user_id: UUID, now: datetime) -> None:
        self._session.execute(
            update(UserSessionRecord)
            .where(
                UserSessionRecord.user_id == user_id,
                UserSessionRecord.revoked_at_utc.is_(None),
            )
            .values(revoked_at_utc=now)
        )

    def _append_event(
        self,
        actor: Principal,
        target: UserRecord,
        action: str,
        occurred_at_utc: datetime,
        details: dict[str, object],
    ) -> None:
        self._session.add(
            AdminUserEventRecord(
                id=uuid4(),
                target_user_id=target.id,
                target_worker_id=target.worker_id,
                actor_user_id=UUID(actor.id),
                actor_worker_id=actor.worker_id,
                action=action,
                occurred_at_utc=occurred_at_utc,
                details=details,
            )
        )
        self._session.flush()


def _account_changes(
    record: UserRecord, role: Role, fleet_id: UUID | None, active: bool
) -> dict[str, object]:
    before = {
        "role": record.role,
        "fleet_id": str(record.fleet_id) if record.fleet_id is not None else None,
        "active": record.active,
    }
    after = {"role": role, "fleet_id": str(fleet_id) if fleet_id is not None else None, "active": active}
    return {
        field: {"from": before[field], "to": after[field]}
        for field in before
        if before[field] != after[field]
    }
