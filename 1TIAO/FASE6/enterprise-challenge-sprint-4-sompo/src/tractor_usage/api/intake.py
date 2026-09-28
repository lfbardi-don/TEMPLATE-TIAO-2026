"""Authenticated catalog, operational CSV ingestion, and visual telemetry access."""
from __future__ import annotations

from datetime import timezone
import math
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tractor_usage.api.auth import Principal, current_user
from tractor_usage.api.routes import _authorize_tractor, _require_role, request_session, usage_model
from tractor_usage.api.schemas import CreateTractorRequest
from tractor_usage.application.contracts import ConflictError, NotFoundError
from tractor_usage.application.operational_telemetry import (
    MAX_CSV_BYTES, import_operational_csv, import_summary, parse_operational_csv, validate_intake_tractor, validate_intake_period,
)
from tractor_usage.application.ports import UsageModel
from tractor_usage.infrastructure.models import FleetRecord, TractorRecord, TelemetryImportRecord, TelemetryMissionRecord, TelemetrySampleRecord, ScoredWindowRecord
from tractor_usage.infrastructure.simulated_scenarios import SCENARIOS, scenario_csv

intake_router = APIRouter()


class CsvIntakeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file_name: Annotated[str, Field(min_length=1, max_length=255)]
    csv_text: Annotated[str, Field(min_length=1, max_length=MAX_CSV_BYTES)]
    source_kind: Literal["simulated_csv", "operational_csv"]

    @field_validator("file_name")
    @classmethod
    def validate_file_name(cls, value: str) -> str:
        value = value.strip()
        if not value or "/" in value or "\\" in value or not value.lower().endswith(".csv"):
            raise ValueError("Informe somente o nome de um arquivo .csv.")
        return value


@intake_router.get("/v1/catalog")
def catalog(session: Annotated[Session, Depends(request_session)], principal: Annotated[Principal, Depends(current_user)]):
    statement = select(FleetRecord).order_by(FleetRecord.name)
    if principal.role == "FLEET_MANAGER":
        statement = statement.where(FleetRecord.id == UUID(principal.fleet_id))
    fleets = []
    for fleet in session.scalars(statement):
        tractors = []
        for tractor in session.scalars(select(TractorRecord).where(TractorRecord.fleet_id == fleet.id).order_by(TractorRecord.external_id)):
            latest = session.scalar(select(TelemetryImportRecord).where(TelemetryImportRecord.tractor_id == tractor.id).order_by(TelemetryImportRecord.ended_at_utc.desc()).limit(1))
            count, alerts = session.execute(select(func.count(), func.count().filter(ScoredWindowRecord.hybrid_alert)).where(ScoredWindowRecord.tractor_id == tractor.id)).one()
            tractors.append({
                "id": str(tractor.id), "fleet_id": str(fleet.id), "external_id": tractor.external_id,
                "display_name": tractor.display_name, "model_name": tractor.model_name,
                "source_kind": latest.source_kind if latest else None,
                "latest_observed_at_utc": latest.ended_at_utc if latest else None,
                "import_count": session.scalar(select(func.count()).select_from(TelemetryImportRecord).where(TelemetryImportRecord.tractor_id == tractor.id)),
                "window_count": count, "alert_count": alerts,
            })
        fleets.append({"id": str(fleet.id), "name": fleet.name, "tractors": tractors})
    return {"fleets": fleets}


@intake_router.post("/v1/fleets/{fleet_id}/tractors", status_code=201)
def create_tractor(fleet_id: UUID, payload: CreateTractorRequest,
                   session: Annotated[Session, Depends(request_session)], principal: Annotated[Principal, Depends(current_user)]):
    _require_role(principal, "INSURER")
    if session.get(FleetRecord, fleet_id) is None:
        raise NotFoundError("fleet not found")
    record = TractorRecord(fleet_id=fleet_id, external_id=payload.external_id, display_name=payload.display_name, model_name="Fendt 314")
    session.add(record)
    try:
        session.flush()
        result = {"id": str(record.id), "fleet_id": str(fleet_id), "external_id": record.external_id,
                  "display_name": record.display_name, "model_name": record.model_name}
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(status_code=409, detail="Já existe uma máquina com essa identificação na frota.") from error
    return result


@intake_router.post("/v1/tractors/{tractor_id}/imports/preview")
def preview_import(tractor_id: UUID, payload: CsvIntakeRequest,
                   session: Annotated[Session, Depends(request_session)], principal: Annotated[Principal, Depends(current_user)]):
    _require_role(principal, "INSURER")
    try:
        validate_intake_tractor(session, str(tractor_id), payload.source_kind)
        parsed = parse_operational_csv(payload.csv_text, str(tractor_id), payload.source_kind)
        duplicate = validate_intake_period(session, str(tractor_id), parsed)
        return {**parsed.preview(payload.source_kind), "duplicate": duplicate}
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except ConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@intake_router.post("/v1/tractors/{tractor_id}/imports")
def submit_import(tractor_id: UUID, payload: CsvIntakeRequest,
                  session: Annotated[Session, Depends(request_session)], model: Annotated[UsageModel, Depends(usage_model)],
                  principal: Annotated[Principal, Depends(current_user)]):
    _require_role(principal, "INSURER")
    try:
        result = import_operational_csv(session, model, tractor_id=str(tractor_id),
            file_name=payload.file_name, csv_text=payload.csv_text, source_kind=payload.source_kind, worker_id=principal.worker_id)
        session.commit()
    except ValueError as error:
        session.rollback()
        raise HTTPException(status_code=422, detail=str(error)) from error
    except (ConflictError, IntegrityError) as error:
        session.rollback()
        raise HTTPException(status_code=409, detail=str(error) if isinstance(error, ConflictError) else "Conteúdo conflitante; atualize e tente novamente.") from error
    return JSONResponse(status_code=200 if result["duplicate"] else 201, content=jsonable_encoder(result))


@intake_router.get("/v1/tractors/{tractor_id}/imports")
def list_imports(tractor_id: UUID, session: Annotated[Session, Depends(request_session)], principal: Annotated[Principal, Depends(current_user)]):
    _authorize_tractor(session, principal, str(tractor_id))
    _require_role(principal, "ADMIN", "INSURER")
    records = session.scalars(select(TelemetryImportRecord).where(TelemetryImportRecord.tractor_id == tractor_id).order_by(TelemetryImportRecord.created_at_utc.desc()))
    return {"imports": [import_summary(session, record) for record in records]}


@intake_router.get("/v1/demo/csv-scenarios")
def csv_scenarios(_: Annotated[Principal, Depends(current_user)]):
    return {"scenarios": [{**item, "download_url": f"/v1/demo/csv-scenarios/{item['id']}.csv"} for item in SCENARIOS]}


@intake_router.get("/v1/demo/csv-scenarios/{scenario_id}.csv")
def download_scenario(scenario_id: str, _: Annotated[Principal, Depends(current_user)]):
    scenario = next((item for item in SCENARIOS if item["id"] == scenario_id), None)
    if scenario is None:
        raise NotFoundError("scenario not found")
    return Response(scenario_csv(scenario_id), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename={scenario['file_name']}"})


@intake_router.get("/v1/tractors/{tractor_id}/telemetry-chart")
def telemetry_chart(tractor_id: UUID, session: Annotated[Session, Depends(request_session)],
                    principal: Annotated[Principal, Depends(current_user)],
                    import_id: UUID | None = None, mission_index: int | None = None,
                    limit: Annotated[int, Query(ge=30, le=1000)] = 300):
    _authorize_tractor(session, principal, str(tractor_id))
    periods = [{"import_id": str(period.id), "mission_index": mission.mission_index,
                "started_at_utc": mission.started_at_utc, "ended_at_utc": mission.ended_at_utc,
                "source_kind": period.source_kind}
               for period, mission in session.execute(select(TelemetryImportRecord, TelemetryMissionRecord)
                   .join(TelemetryMissionRecord, TelemetryMissionRecord.import_id == TelemetryImportRecord.id)
                   .where(TelemetryImportRecord.tractor_id == tractor_id)
                   .order_by(TelemetryMissionRecord.started_at_utc.desc()))]
    imports = select(TelemetryImportRecord).where(TelemetryImportRecord.tractor_id == tractor_id)
    if import_id is not None:
        imports = imports.where(TelemetryImportRecord.id == import_id)
    record = session.scalar(imports.order_by(TelemetryImportRecord.ended_at_utc.desc()).limit(1))
    if record is None:
        if import_id is not None:
            raise NotFoundError("telemetry import not found")
        return {"import_id": None, "mission_index": None, "source_kind": None, "total_samples": 0, "samples": [], "periods": [], "sampling_method": "evenly_spaced", "sampled_count": 0}
    if mission_index is None:
        mission_index = session.scalar(select(func.max(TelemetrySampleRecord.mission_index)).where(TelemetrySampleRecord.import_id == record.id))
    base = select(TelemetrySampleRecord).where(TelemetrySampleRecord.import_id == record.id, TelemetrySampleRecord.mission_index == mission_index)
    count = session.scalar(select(func.count()).select_from(base.subquery())) or 0
    if count == 0:
        raise NotFoundError("telemetry mission not found")
    # Sample a full mission evenly in SQL, keeping the response bounded. Episode
    # detail remains the exact 1 Hz evidence; these points are a browsing overview.
    ranked = select(TelemetrySampleRecord.position_deciseconds,
                    func.row_number().over(order_by=TelemetrySampleRecord.position_deciseconds).label("row_number")
                    ).where(TelemetrySampleRecord.import_id == record.id, TelemetrySampleRecord.mission_index == mission_index).subquery()
    step = max(1, math.ceil(count / limit))
    positions = select(ranked.c.position_deciseconds).where((ranked.c.row_number - 1) % step == 0)
    rows = session.scalars(base.where(TelemetrySampleRecord.position_deciseconds.in_(positions)).order_by(TelemetrySampleRecord.position_deciseconds).limit(limit))
    fields = ("engine_rpm", "actual_engine_torque_pct", "engine_load_pct", "coolant_temp_c", "ground_machine_speed_mps", "rear_pto_rpm")
    samples = []
    for sample in rows:
        wheel, ground = sample.wheel_machine_speed_mps, sample.ground_machine_speed_mps
        slip = min(100.0, max(-100.0, 100 * (wheel - ground) / wheel)) if wheel is not None and ground is not None and wheel >= .5 else None
        samples.append({"observed_at_utc": sample.observed_at_utc.astimezone(timezone.utc), **{name: getattr(sample, name) for name in fields}, "traction_slip_pct": slip})
    return {"import_id": str(record.id), "mission_index": mission_index, "source_kind": record.source_kind, "total_samples": count, "samples": samples, "periods": periods, "sampling_method": "evenly_spaced", "sampled_count": len(samples)}
