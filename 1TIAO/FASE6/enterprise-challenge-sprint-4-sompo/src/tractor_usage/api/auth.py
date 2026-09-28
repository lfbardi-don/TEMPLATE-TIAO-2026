"""Browser login and request authentication for the local inspection API."""

from __future__ import annotations

from dataclasses import asdict
from hmac import compare_digest
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from tractor_usage.application.auth import Principal
from tractor_usage.infrastructure.auth_repository import AuthRepository, SESSION_TTL


SESSION_COOKIE = "inspection_session"
auth_router = APIRouter()


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    worker_id: Annotated[str, Field(min_length=1, max_length=20, pattern=r"^[0-9]+$")]
    password: Annotated[str, Field(min_length=1, max_length=4096)]


def _same_origin_for_write(request: Request) -> None:
    if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
        return
    origin = request.headers.get("origin")
    if origin is None:
        return
    supplied = urlsplit(origin)
    actual = urlsplit(str(request.url))
    if supplied.scheme != actual.scheme or supplied.netloc != actual.netloc:
        raise HTTPException(status_code=403, detail="request origin is not allowed")


def current_user(request: Request) -> Principal:
    """Resolve an active browser session on every protected request."""

    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="authentication required")
    _same_origin_for_write(request)
    with request.app.state.session_factory() as session:
        principal = AuthRepository(session).principal_for_session(token)
    if principal is None:
        raise HTTPException(status_code=401, detail="authentication required")
    return principal


def require_ingest_token(
    request: Request,
    x_ingest_token: Annotated[str | None, Header(alias="X-Ingest-Token")] = None,
) -> None:
    """Accept only the server-configured machine token for window ingestion."""

    expected = getattr(request.app.state, "ingest_token", None)
    if not expected:
        raise HTTPException(status_code=503, detail="ingestion credential is not configured")
    if x_ingest_token is None or not compare_digest(x_ingest_token, expected):
        raise HTTPException(status_code=401, detail="invalid ingestion credential")


@auth_router.post("/v1/auth/login")
def login(request: Request, payload: LoginRequest):
    with request.app.state.session_factory() as session:
        repository = AuthRepository(session)
        principal = repository.authenticate(payload.worker_id, payload.password)
        if principal is None:
            raise HTTPException(status_code=401, detail="invalid credentials")
        token = repository.create_session(principal.id)
    response = JSONResponse(content=asdict(principal))
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=int(SESSION_TTL.total_seconds()),
        httponly=True,
        secure=request.app.state.auth_cookie_secure,
        samesite="lax",
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@auth_router.get("/v1/auth/me")
def me(principal: Annotated[Principal, Depends(current_user)]):
    return asdict(principal)


@auth_router.post("/v1/auth/logout", status_code=204)
def logout(
    request: Request,
    _: Annotated[Principal, Depends(current_user)],
):
    token = request.cookies[SESSION_COOKIE]
    with request.app.state.session_factory() as session:
        AuthRepository(session).revoke_session(token)
    response = Response(status_code=204)
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.headers["Cache-Control"] = "no-store"
    return response
