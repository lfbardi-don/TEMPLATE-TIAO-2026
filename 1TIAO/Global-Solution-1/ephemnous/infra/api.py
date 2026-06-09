"""API FastAPI do ephemnous.

GET  /healthz: sanidade (banco + migracao)
POST /telemetry: telemetria entra, comando volta na resposta (laco fechado)
POST /admin/inject_eclipse: fallback do gatilho ao vivo (Fase 4)

O backend e dono do estado fisico de cada no (em memoria, no processo) e da fisica.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ephemnous.core import physics
from ephemnous.core.forecaster import Forecaster, PersistenceForecaster
from ephemnous.core.models import History, NodeParams, NodeState, Telemetry
from ephemnous.infra import db, repo
from ephemnous.services import control_loop

_params = NodeParams()
_forecaster: Forecaster = PersistenceForecaster()  # trocado por ML no startup, se disponivel
_states: dict[int, NodeState] = {}      # estado fisico atual por node_id
_history: dict[int, History] = {}       # janela de historico por node_id (lags do ML)
_node_ids: dict[str, int] = {}          # cache nome -> node_id
_forced_eclipse: set[str] = set()       # nos com eclipse forcado via /admin (Fase 4)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _forecaster
    db.open_pool()
    try:
        from ephemnous.infra.ml_forecaster import MLForecaster
        _forecaster = MLForecaster()
        print("[ephemnous] forecaster: ML (HistGradientBoosting)")
    except Exception as exc:  # modelo ausente/invalido -> stub
        _forecaster = PersistenceForecaster()
        print(f"[ephemnous] forecaster: persistencia stub (ML indisponivel: {exc})")
    try:
        yield
    finally:
        db.close_pool()


def _history_for(node_id: int) -> History:
    h = _history.get(node_id)
    if h is None:
        f_ecl = physics.eclipse_fraction(_params.beta_deg, _params.altitude_km)
        h = History([], [], [], [], [], _params.beta_deg, f_ecl, _params.orbit_period_s)
        _history[node_id] = h
    return h


app = FastAPI(title="ephemnous", version="0.1.0", lifespan=lifespan)


class TelemetryIn(BaseModel):
    node_id: str = Field(..., description="nome do no (ex.: wokwi-0, sim-1)")
    ts: int | None = None
    irradiance_frac: float = 1.0
    force_eclipse: bool = False
    temp_k: float | None = None
    load_frac: float = 0.0
    state: str = "idle"
    lookahead: int = 3            # 0 = modo burro
    mode: str = "mpc"


class CommandOut(BaseModel):
    action: str
    target_pwm: int
    reason: str
    decision_id: int


def _node_id_for(name: str) -> int:
    nid = _node_ids.get(name)
    if nid is None:
        kind = "wokwi" if name.startswith("wokwi") else "sim"
        nid = repo.get_or_create_node(name, kind, {"profile": "default"})
        _node_ids[name] = nid
    return nid


@app.get("/healthz")
def healthz() -> JSONResponse:
    try:
        ok = db.ping()
        tables = db.list_tables()
    except Exception as exc:
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "db": False, "error": str(exc)},
        )
    return JSONResponse(content={"status": "ok", "db": ok, "tables": tables})


@app.post("/telemetry", response_model=CommandOut)
def post_telemetry(t: TelemetryIn) -> CommandOut:
    node_id = _node_id_for(t.node_id)
    prev = _states.get(node_id) or physics.initial_state(_params)

    tel = Telemetry(
        node_name=t.node_id,
        irradiance_frac=t.irradiance_frac,
        force_eclipse=t.force_eclipse or (t.node_id in _forced_eclipse),
        temp_k=t.temp_k,
        load_frac=t.load_frac,
        state=t.state,
        ts_device=t.ts,
    )

    result = control_loop.step(prev, tel, _params, _forecaster, _history_for(node_id),
                               lookahead=t.lookahead, mode=t.mode)
    _states[node_id] = result.state

    repo.save_telemetry(node_id, tel)
    repo.save_node_state(node_id, result.state)
    fid = repo.save_forecast(node_id, result.forecast)
    did = repo.save_decision(node_id, result.decision, fid)

    return CommandOut(
        action=result.decision.action,
        target_pwm=result.decision.target_pwm,
        reason=result.decision.reason,
        decision_id=did,
    )


@app.post("/admin/inject_eclipse")
def inject_eclipse(node_id: str, on: bool = True) -> dict:
    """Forca ou solta eclipse para um no, independente do Wokwi."""
    if on:
        _forced_eclipse.add(node_id)
    else:
        _forced_eclipse.discard(node_id)
    return {"node_id": node_id, "force_eclipse": on}
