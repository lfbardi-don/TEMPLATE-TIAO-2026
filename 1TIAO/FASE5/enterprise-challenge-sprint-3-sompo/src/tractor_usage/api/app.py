"""FastAPI wiring and process-lifetime resource ownership."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from tractor_usage.api.routes import router
from tractor_usage.application.contracts import (
    ConflictError,
    InvalidInspectionTransitionError,
    ModelUnavailableError,
    NotFoundError,
    StaleInspectionCaseVersionError,
)
from tractor_usage.application.ports import ReplayProgressReader, UsageModel
from tractor_usage.infrastructure.database import Settings, create_database_engine, create_session_factory
from tractor_usage.infrastructure.frozen_model import FrozenBundleUsageModel


def create_app(
    *,
    settings: Settings | None = None,
    usage_model: UsageModel | None = None,
    engine=None,
    replay_progress: ReplayProgressReader | None = None,
) -> FastAPI:
    configured = settings or Settings.from_environment()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        owned_engine = None
        try:
            resolved_model = usage_model or FrozenBundleUsageModel.load(configured.model_dir)
            owned_engine = engine or create_database_engine(configured.database_url)
            app.state.engine = owned_engine
            app.state.session_factory = create_session_factory(owned_engine)
            app.state.usage_model = resolved_model
            if replay_progress is not None:
                app.state.replay_progress = replay_progress
            yield
        finally:
            if engine is None and owned_engine is not None:
                owned_engine.dispose()

    app = FastAPI(
        title="Preventive Inspection API",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.include_router(router)
    _register_error_handlers(app)
    return app


def _register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(NotFoundError)
    def not_found(_: Request, __: NotFoundError):
        return JSONResponse(status_code=404, content={"detail": "resource not found"})

    @app.exception_handler(ConflictError)
    def conflict(_: Request, __: ConflictError):
        return JSONResponse(status_code=409, content={"detail": "conflicting persistent state"})

    @app.exception_handler(StaleInspectionCaseVersionError)
    def stale_inspection_case(_: Request, __: StaleInspectionCaseVersionError):
        return JSONResponse(
            status_code=409,
            content={
                "code": "STALE_INSPECTION_CASE_VERSION",
                "detail": "inspection case was modified; refresh and retry",
            },
        )

    @app.exception_handler(InvalidInspectionTransitionError)
    def invalid_inspection_transition(_: Request, __: InvalidInspectionTransitionError):
        return JSONResponse(
            status_code=409,
            content={
                "code": "INVALID_INSPECTION_TRANSITION",
                "detail": "inspection case transition is not allowed",
            },
        )

    @app.exception_handler(ModelUnavailableError)
    def model_unavailable(_: Request, __: ModelUnavailableError):
        return JSONResponse(status_code=500, content={"detail": "approved model unavailable"})

    @app.exception_handler(SQLAlchemyError)
    def database_unavailable(_: Request, __: SQLAlchemyError):
        return JSONResponse(status_code=503, content={"detail": "database unavailable"})


app = create_app()
