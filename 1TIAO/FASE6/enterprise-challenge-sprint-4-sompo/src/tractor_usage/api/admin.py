"""Administrator-only account management and account action history."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator
from sqlalchemy.orm import Session

from tractor_usage.api.auth import current_user
from tractor_usage.api.routes import request_session
from tractor_usage.application.auth import AdminAccount, AdminUserEvent, Principal, Role
from tractor_usage.infrastructure.admin_repository import AdminAccountRepository


admin_router = APIRouter()


class AccountAccessRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Role
    fleet_id: UUID | None

    @model_validator(mode="after")
    def valid_fleet_scope(self):
        if (self.role == "FLEET_MANAGER") != (self.fleet_id is not None):
            raise ValueError("only fleet managers require a fleet_id")
        return self


class CreateAdminUserRequest(AccountAccessRequest):
    worker_id: Annotated[str, Field(min_length=1, max_length=20, pattern=r"^[0-9]+$")]


class UpdateAdminUserRequest(AccountAccessRequest):
    active: StrictBool


def _admin(principal: Principal) -> None:
    if principal.role != "ADMIN":
        raise HTTPException(status_code=403, detail="administrator access required")


def _account(value: AdminAccount) -> dict[str, object]:
    return {
        "id": value.id,
        "worker_id": value.worker_id,
        "role": value.role,
        "fleet_id": value.fleet_id,
        "active": value.active,
        "created_at_utc": value.created_at_utc.isoformat(),
    }


def _event(value: AdminUserEvent) -> dict[str, object]:
    return {
        "id": value.id,
        "target_user_id": value.target_user_id,
        "target_worker_id": value.target_worker_id,
        "actor_user_id": value.actor_user_id,
        "actor_worker_id": value.actor_worker_id,
        "action": value.action,
        "occurred_at_utc": value.occurred_at_utc.isoformat(),
        "details": dict(value.details),
    }


@admin_router.get("/v1/admin/users")
def list_users(
    response: Response,
    session: Annotated[Session, Depends(request_session)],
    principal: Annotated[Principal, Depends(current_user)],
):
    _admin(principal)
    response.headers["Cache-Control"] = "no-store"
    return {"users": [_account(user) for user in AdminAccountRepository(session).list_users()]}


@admin_router.get("/v1/admin/catalog")
def list_catalog(
    response: Response,
    session: Annotated[Session, Depends(request_session)],
    principal: Annotated[Principal, Depends(current_user)],
):
    _admin(principal)
    response.headers["Cache-Control"] = "no-store"
    return {"fleets": AdminAccountRepository(session).list_catalog()}


@admin_router.post("/v1/admin/users", status_code=201)
def create_user(
    payload: CreateAdminUserRequest,
    response: Response,
    session: Annotated[Session, Depends(request_session)],
    principal: Annotated[Principal, Depends(current_user)],
):
    _admin(principal)
    user, temporary_password = AdminAccountRepository(session).create_user(
        actor=principal,
        worker_id=payload.worker_id,
        role=payload.role,
        fleet_id=str(payload.fleet_id) if payload.fleet_id is not None else None,
    )
    response.headers["Cache-Control"] = "no-store"
    return {"user": _account(user), "temporary_password": temporary_password}


@admin_router.patch("/v1/admin/users/{user_id}")
def update_user(
    user_id: UUID,
    payload: UpdateAdminUserRequest,
    response: Response,
    session: Annotated[Session, Depends(request_session)],
    principal: Annotated[Principal, Depends(current_user)],
):
    _admin(principal)
    user = AdminAccountRepository(session).update_user(
        actor=principal,
        user_id=str(user_id),
        role=payload.role,
        fleet_id=str(payload.fleet_id) if payload.fleet_id is not None else None,
        active=payload.active,
    )
    response.headers["Cache-Control"] = "no-store"
    return {"user": _account(user)}


@admin_router.post("/v1/admin/users/{user_id}/reset-password")
def reset_password(
    user_id: UUID,
    response: Response,
    session: Annotated[Session, Depends(request_session)],
    principal: Annotated[Principal, Depends(current_user)],
):
    _admin(principal)
    temporary_password = AdminAccountRepository(session).reset_password(
        actor=principal, user_id=str(user_id)
    )
    response.headers["Cache-Control"] = "no-store"
    return {"temporary_password": temporary_password}


@admin_router.get("/v1/admin/user-events")
def list_user_events(
    response: Response,
    session: Annotated[Session, Depends(request_session)],
    principal: Annotated[Principal, Depends(current_user)],
):
    _admin(principal)
    response.headers["Cache-Control"] = "no-store"
    return {"events": [_event(event) for event in AdminAccountRepository(session).list_events()]}
