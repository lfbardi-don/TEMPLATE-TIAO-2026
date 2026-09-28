"""Synchronous HTTP routes and request-scoped dependencies."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from tractor_usage.api.schemas import (
    CompleteWindowRequest,
    CreateInspectionCaseRequest,
    CreateFleetRequest,
    episode_detail_response,
    exposure_timeline_response,
    fleet_overview_response,
    fleet_registration_response,
    ingest_response,
    inspection_case_response,
    inspection_case_events_response,
    inspection_cases_response,
    portfolio_response,
    replay_progress_response,
    tractor_overview_response,
    telemetry_periods_response,
    UpdateInspectionCaseRequest,
)
from tractor_usage.api.auth import Principal, current_user, require_ingest_token
from tractor_usage.application.contracts import NotFoundError
from tractor_usage.application.evidence import (
    GetEpisodeDetailUseCase,
    GetExposureTimelineUseCase,
)
from tractor_usage.application.ports import ReplayProgressReader, UsageModel
from tractor_usage.application.use_cases import (
    CreateFleetUseCase,
    GetFleetOverviewUseCase,
    GetPortfolioPrioritiesUseCase,
    GetTractorOverviewUseCase,
    IngestWindowUseCase,
)
from tractor_usage.application.telemetry import GetTelemetryPeriodsUseCase
from tractor_usage.application.inspection_cases import (
    CreateInspectionCaseUseCase,
    GetInspectionCasesUseCase,
    UpdateInspectionCaseUseCase,
)
from tractor_usage.infrastructure.inspection_case_repository import PostgresInspectionCaseRepository
from tractor_usage.infrastructure.auth_repository import AuthRepository
from tractor_usage.infrastructure.postgres_telemetry_replay import PostgresEpisodeSamples
from tractor_usage.infrastructure.repositories import PostgresInspectionRepository
from tractor_usage.infrastructure.telemetry_repository import PostgresTelemetryRepository


router = APIRouter()


def _require_role(principal: Principal, *roles: str) -> None:
    if principal.role not in roles:
        raise HTTPException(status_code=403, detail="access denied")


def _validate_assignee(session: Session, worker_id: str | None) -> None:
    if worker_id is not None and not AuthRepository(session).is_active_inspector(worker_id):
        raise HTTPException(status_code=422, detail="assignee must be an active inspector")


def _authorize_fleet(session: Session, principal: Principal, fleet_id: str) -> None:
    repository = PostgresInspectionRepository(session)
    if repository.get_fleet(fleet_id) is None:
        raise NotFoundError("fleet not found")
    if principal.role == "FLEET_MANAGER" and principal.fleet_id != fleet_id:
        raise NotFoundError("fleet not found")


def _authorize_tractor(session: Session, principal: Principal, tractor_id: str) -> None:
    repository = PostgresInspectionRepository(session)
    tractor = repository.get_tractor(tractor_id)
    if tractor is None:
        raise NotFoundError("tractor not found")
    if principal.role == "FLEET_MANAGER" and principal.fleet_id != tractor.fleet_id:
        raise NotFoundError("tractor not found")


def request_session(request: Request):
    factory = request.app.state.session_factory
    with factory() as session:
        yield session


def usage_model(request: Request) -> UsageModel:
    return request.app.state.usage_model


def replay_progress_reader(request: Request) -> ReplayProgressReader | None:
    return getattr(request.app.state, "replay_progress", None)


def _as_of_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        raise HTTPException(status_code=422, detail="as_of_utc must include a timezone")
    return value.astimezone(timezone.utc)


@router.post("/v1/fleets", status_code=201)
def create_fleet(
    payload: CreateFleetRequest,
    session: Annotated[Session, Depends(request_session)],
    principal: Annotated[Principal, Depends(current_user)],
):
    _require_role(principal, "INSURER")
    result = CreateFleetUseCase(PostgresInspectionRepository(session)).execute(
        payload.to_contract()
    )
    return fleet_registration_response(result)


@router.post("/v1/tractors/{tractor_id}/windows")
def ingest_window(
    tractor_id: UUID,
    payload: CompleteWindowRequest,
    session: Annotated[Session, Depends(request_session)],
    model: Annotated[UsageModel, Depends(usage_model)],
    _: Annotated[None, Depends(require_ingest_token)],
):
    result = IngestWindowUseCase(PostgresInspectionRepository(session), model).execute(
        str(tractor_id), payload.to_contract()
    )
    return JSONResponse(
        status_code=200 if result.duplicate else 201,
        content=ingest_response(result),
    )


@router.get("/v1/portfolio/inspection-priorities")
def portfolio_priorities(
    as_of_utc: Annotated[datetime | None, Query()] = None,
    *,
    session: Annotated[Session, Depends(request_session)],
    model: Annotated[UsageModel, Depends(usage_model)],
    principal: Annotated[Principal, Depends(current_user)],
):
    result = GetPortfolioPrioritiesUseCase(
        PostgresInspectionRepository(session), model
    ).execute(
        as_of_utc=_as_of_utc(as_of_utc),
        fleet_id=principal.fleet_id if principal.role == "FLEET_MANAGER" else None,
    )
    return portfolio_response(result)


@router.get("/v1/fleets/{fleet_id}/overview")
def fleet_overview(
    fleet_id: UUID,
    as_of_utc: Annotated[datetime | None, Query()] = None,
    *,
    session: Annotated[Session, Depends(request_session)],
    model: Annotated[UsageModel, Depends(usage_model)],
    principal: Annotated[Principal, Depends(current_user)],
):
    _authorize_fleet(session, principal, str(fleet_id))
    _require_role(principal, "ADMIN", "INSURER", "FLEET_MANAGER")
    result = GetFleetOverviewUseCase(PostgresInspectionRepository(session), model).execute(
        str(fleet_id), as_of_utc=_as_of_utc(as_of_utc)
    )
    return fleet_overview_response(result)


@router.get("/v1/tractors/{tractor_id}/overview")
def tractor_overview(
    tractor_id: UUID,
    as_of_utc: Annotated[datetime | None, Query()] = None,
    *,
    session: Annotated[Session, Depends(request_session)],
    model: Annotated[UsageModel, Depends(usage_model)],
    principal: Annotated[Principal, Depends(current_user)],
):
    _authorize_tractor(session, principal, str(tractor_id))
    result = GetTractorOverviewUseCase(
        PostgresInspectionRepository(session), model,
        PostgresInspectionCaseRepository(session) if principal.role != "FLEET_MANAGER" else None,
    ).execute(
        str(tractor_id), as_of_utc=_as_of_utc(as_of_utc)
    )
    return tractor_overview_response(result)


@router.get("/v1/tractors/{tractor_id}/episodes/{episode_id}")
def episode_detail(
    tractor_id: UUID,
    episode_id: Annotated[str, Path(pattern=r"^[0-9a-f]{20}$")],
    as_of_utc: Annotated[datetime | None, Query()] = None,
    *,
    session: Annotated[Session, Depends(request_session)],
    model: Annotated[UsageModel, Depends(usage_model)],
    principal: Annotated[Principal, Depends(current_user)],
):
    _authorize_tractor(session, principal, str(tractor_id))
    result = GetEpisodeDetailUseCase(
        PostgresInspectionRepository(session), model, PostgresEpisodeSamples(session)
    ).execute(str(tractor_id), episode_id, as_of_utc=_as_of_utc(as_of_utc))
    return episode_detail_response(result)


@router.get("/v1/tractors/{tractor_id}/exposure-timeline")
def exposure_timeline(
    tractor_id: UUID,
    as_of_utc: Annotated[datetime | None, Query()] = None,
    *,
    session: Annotated[Session, Depends(request_session)],
    principal: Annotated[Principal, Depends(current_user)],
):
    _authorize_tractor(session, principal, str(tractor_id))
    result = GetExposureTimelineUseCase(PostgresInspectionRepository(session)).execute(
        str(tractor_id), as_of_utc=_as_of_utc(as_of_utc)
    )
    return exposure_timeline_response(result)


@router.get("/v1/tractors/{tractor_id}/telemetry-periods")
def telemetry_periods(
    tractor_id: UUID,
    import_id: UUID | None = Query(default=None),
    *,
    session: Annotated[Session, Depends(request_session)],
    principal: Annotated[Principal, Depends(current_user)],
):
    _authorize_tractor(session, principal, str(tractor_id))
    _require_role(principal, "ADMIN", "INSURER")
    result = GetTelemetryPeriodsUseCase(PostgresTelemetryRepository(session)).execute(
        str(tractor_id), import_id=str(import_id) if import_id is not None else None
    )
    return telemetry_periods_response(result)


@router.get("/v1/demo/replay-progress", responses={204: {"description": "No replay is active"}})
def demo_replay_progress(
    principal: Annotated[Principal, Depends(current_user)],
    reader: Annotated[ReplayProgressReader | None, Depends(replay_progress_reader)],
    session: Annotated[Session, Depends(request_session)],
):
    if reader is None:
        return Response(status_code=204)
    progress = reader.snapshot()
    _authorize_tractor(session, principal, progress.tractor_id)
    return replay_progress_response(progress)


@router.post("/v1/tractors/{tractor_id}/inspection-cases", status_code=201)
def create_inspection_case(
    tractor_id: UUID,
    payload: CreateInspectionCaseRequest,
    session: Annotated[Session, Depends(request_session)],
    model: Annotated[UsageModel, Depends(usage_model)],
    principal: Annotated[Principal, Depends(current_user)],
):
    def authorize_tractor(tractor) -> None:
        if principal.role == "FLEET_MANAGER" and principal.fleet_id != tractor.fleet_id:
            raise NotFoundError("tractor not found")
        _require_role(principal, "INSURER")
        _validate_assignee(session, payload.assignee)

    result = CreateInspectionCaseUseCase(
        PostgresInspectionCaseRepository(session),
        PostgresInspectionRepository(session),
        PostgresTelemetryRepository(session),
        model,
    ).execute(
        str(tractor_id), payload.to_contract(), authorize_tractor=authorize_tractor,
        actor=principal,
    )
    return inspection_case_response(result)


@router.get("/v1/inspectors")
def active_inspectors(
    response: Response,
    session: Annotated[Session, Depends(request_session)],
    principal: Annotated[Principal, Depends(current_user)],
):
    _require_role(principal, "ADMIN", "INSURER")
    response.headers["Cache-Control"] = "no-store"
    return {
        "inspectors": [
            {"id": inspector.id, "worker_id": inspector.worker_id}
            for inspector in AuthRepository(session).list_active_inspectors()
        ]
    }


@router.get("/v1/tractors/{tractor_id}/inspection-cases")
def inspection_cases(
    tractor_id: UUID,
    session: Annotated[Session, Depends(request_session)],
    principal: Annotated[Principal, Depends(current_user)],
):
    _authorize_tractor(session, principal, str(tractor_id))
    _require_role(principal, "ADMIN", "INSURER", "INSPECTOR")
    result = GetInspectionCasesUseCase(PostgresInspectionCaseRepository(session)).list(
        str(tractor_id)
    )
    return inspection_cases_response(result)


@router.get("/v1/inspection-cases")
def all_inspection_cases(
    session: Annotated[Session, Depends(request_session)],
    principal: Annotated[Principal, Depends(current_user)],
):
    _require_role(principal, "ADMIN", "INSURER", "INSPECTOR")
    return inspection_cases_response(
        GetInspectionCasesUseCase(PostgresInspectionCaseRepository(session)).list()
    )


@router.get("/v1/inspection-cases/{case_id}/episodes/{episode_id}")
def inspection_case_episode(
    case_id: UUID,
    episode_id: Annotated[str, Path(pattern=r"^[0-9a-f]{20}$")],
    session: Annotated[Session, Depends(request_session)],
    model: Annotated[UsageModel, Depends(usage_model)],
    principal: Annotated[Principal, Depends(current_user)],
):
    _require_role(principal, "ADMIN", "INSURER", "INSPECTOR")
    case = GetInspectionCasesUseCase(PostgresInspectionCaseRepository(session)).get(str(case_id))
    episodes = case.evidence_snapshot.get("episodes_last_30_days", [])
    if not any(item.get("id") == episode_id for item in episodes):
        raise NotFoundError("episode not found in inspection evidence")
    result = GetEpisodeDetailUseCase(
        PostgresInspectionRepository(session), model, PostgresEpisodeSamples(session)
    ).execute(case.tractor_id, episode_id, as_of_utc=case.evidence_as_of_utc)
    return episode_detail_response(result)


@router.get("/v1/inspection-cases/{case_id}")
def inspection_case(
    case_id: UUID,
    session: Annotated[Session, Depends(request_session)],
    principal: Annotated[Principal, Depends(current_user)],
):
    case = PostgresInspectionCaseRepository(session).get_case(str(case_id))
    if case is None:
        raise NotFoundError("inspection case not found")
    _authorize_tractor(session, principal, case.tractor_id)
    _require_role(principal, "ADMIN", "INSURER", "INSPECTOR")
    return inspection_case_response(case)


@router.patch("/v1/inspection-cases/{case_id}")
def update_inspection_case(
    case_id: UUID,
    payload: UpdateInspectionCaseRequest,
    session: Annotated[Session, Depends(request_session)],
    principal: Annotated[Principal, Depends(current_user)],
):
    def authorize_case(case) -> None:
        _authorize_tractor(session, principal, case.tractor_id)
        if payload.action in ("UPDATE", "CANCEL"):
            _require_role(principal, "INSURER")
        else:
            _require_role(principal, "INSPECTOR")
            if (
                ("assignee" in payload.model_fields_set and payload.assignee != case.assignee)
                or (
                    "due_date" in payload.model_fields_set
                    and (payload.due_date.isoformat() if payload.due_date else None) != case.due_date
                )
            ):
                raise HTTPException(status_code=403, detail="inspector cannot change assignment")
        if "assignee" in payload.model_fields_set and payload.assignee != case.assignee:
            _validate_assignee(session, payload.assignee)

    return inspection_case_response(
        UpdateInspectionCaseUseCase(PostgresInspectionCaseRepository(session)).execute(
            str(case_id), payload.to_contract(), authorize_case=authorize_case,
            actor=principal,
        )
    )


@router.get("/v1/inspection-cases/{case_id}/events")
def inspection_case_events(
    case_id: UUID,
    session: Annotated[Session, Depends(request_session)],
    principal: Annotated[Principal, Depends(current_user)],
):
    repository = PostgresInspectionCaseRepository(session)
    case = repository.get_case(str(case_id))
    if case is None:
        raise NotFoundError("inspection case not found")
    _authorize_tractor(session, principal, case.tractor_id)
    _require_role(principal, "ADMIN")
    return inspection_case_events_response(str(case_id), repository.list_events(str(case_id)))


@router.get("/health/live")
def health_live():
    return {"status": "live"}


@router.get("/health/ready")
def health_ready(request: Request):
    try:
        with request.app.state.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return JSONResponse(status_code=503, content={"status": "not_ready"})
    return {"status": "ready"}
