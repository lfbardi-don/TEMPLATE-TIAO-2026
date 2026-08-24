"""Synchronous HTTP routes and request-scoped dependencies."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from tractor_usage.api.schemas import (
    CompleteWindowRequest,
    CreateInspectionCaseRequest,
    CreateFleetRequest,
    fleet_overview_response,
    fleet_registration_response,
    ingest_response,
    inspection_case_response,
    inspection_cases_response,
    portfolio_response,
    replay_progress_response,
    tractor_overview_response,
    telemetry_periods_response,
    UpdateInspectionCaseRequest,
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
from tractor_usage.infrastructure.repositories import PostgresInspectionRepository
from tractor_usage.infrastructure.telemetry_repository import PostgresTelemetryRepository


router = APIRouter()


def request_session(request: Request):
    factory = request.app.state.session_factory
    with factory() as session:
        yield session


def usage_model(request: Request) -> UsageModel:
    return request.app.state.usage_model


def replay_progress_reader(request: Request) -> ReplayProgressReader:
    reader = getattr(request.app.state, "replay_progress", None)
    if reader is None:
        raise HTTPException(status_code=404, detail="resource not found")
    return reader


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
):
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
):
    result = GetPortfolioPrioritiesUseCase(
        PostgresInspectionRepository(session), model
    ).execute(as_of_utc=_as_of_utc(as_of_utc))
    return portfolio_response(result)


@router.get("/v1/fleets/{fleet_id}/overview")
def fleet_overview(
    fleet_id: UUID,
    as_of_utc: Annotated[datetime | None, Query()] = None,
    *,
    session: Annotated[Session, Depends(request_session)],
    model: Annotated[UsageModel, Depends(usage_model)],
):
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
):
    result = GetTractorOverviewUseCase(PostgresInspectionRepository(session), model).execute(
        str(tractor_id), as_of_utc=_as_of_utc(as_of_utc)
    )
    return tractor_overview_response(result)


@router.get("/v1/tractors/{tractor_id}/telemetry-periods")
def telemetry_periods(
    tractor_id: UUID,
    import_id: UUID | None = Query(default=None),
    *,
    session: Annotated[Session, Depends(request_session)],
):
    result = GetTelemetryPeriodsUseCase(PostgresTelemetryRepository(session)).execute(
        str(tractor_id), import_id=str(import_id) if import_id is not None else None
    )
    return telemetry_periods_response(result)


@router.get("/v1/demo/replay-progress")
def demo_replay_progress(
    reader: Annotated[ReplayProgressReader, Depends(replay_progress_reader)],
):
    return replay_progress_response(reader.snapshot())


@router.post("/v1/tractors/{tractor_id}/inspection-cases", status_code=201)
def create_inspection_case(
    tractor_id: UUID,
    payload: CreateInspectionCaseRequest,
    session: Annotated[Session, Depends(request_session)],
    model: Annotated[UsageModel, Depends(usage_model)],
):
    result = CreateInspectionCaseUseCase(
        PostgresInspectionCaseRepository(session),
        PostgresInspectionRepository(session),
        PostgresTelemetryRepository(session),
        model,
    ).execute(str(tractor_id), payload.to_contract())
    return inspection_case_response(result)


@router.get("/v1/tractors/{tractor_id}/inspection-cases")
def inspection_cases(
    tractor_id: UUID,
    session: Annotated[Session, Depends(request_session)],
):
    result = GetInspectionCasesUseCase(PostgresInspectionCaseRepository(session)).list(
        str(tractor_id)
    )
    return inspection_cases_response(result)


@router.get("/v1/inspection-cases/{case_id}")
def inspection_case(
    case_id: UUID,
    session: Annotated[Session, Depends(request_session)],
):
    return inspection_case_response(
        GetInspectionCasesUseCase(PostgresInspectionCaseRepository(session)).get(str(case_id))
    )


@router.patch("/v1/inspection-cases/{case_id}")
def update_inspection_case(
    case_id: UUID,
    payload: UpdateInspectionCaseRequest,
    session: Annotated[Session, Depends(request_session)],
):
    return inspection_case_response(
        UpdateInspectionCaseUseCase(PostgresInspectionCaseRepository(session)).execute(
            str(case_id), payload.to_contract()
        )
    )


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
