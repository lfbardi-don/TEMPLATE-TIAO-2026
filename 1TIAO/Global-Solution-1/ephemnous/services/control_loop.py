"""Laço de controle: telemetria -> física -> forecast -> MPC -> decisão."""

from __future__ import annotations

from dataclasses import dataclass

from ephemnous.core import physics
from ephemnous.core.forecaster import Forecaster
from ephemnous.core.models import Decision, Forecast, History, NodeParams, NodeState, Telemetry
from ephemnous.core.mpc import decide

HORIZON_STEPS = 5
MAXLEN = 60  # tamanho máximo da janela de histórico


@dataclass
class LoopResult:
    state: NodeState
    forecast: Forecast
    decision: Decision


def step(
    prev_state: NodeState,
    tel: Telemetry,
    params: NodeParams,
    forecaster: Forecaster,
    hist: History,
    lookahead: int = 3,
    mode: str = "mpc",
) -> LoopResult:
    new_state = physics.advance(prev_state, tel, params)

    # adiciona a observação atual à janela (alimenta os lags do ML)
    hist.power.append(new_state.power_avail_w)
    hist.temp.append(new_state.temp_k)
    hist.load.append(tel.load_frac)
    hist.phase.append(new_state.orbit_phase)
    hist.soc.append(new_state.soc_frac)
    if len(hist.power) > MAXLEN:
        for lst in (hist.power, hist.temp, hist.load, hist.phase, hist.soc):
            del lst[: -MAXLEN]

    forecast = forecaster.predict(new_state, hist, HORIZON_STEPS, params.dt_s)
    decision = decide(new_state, forecast, params, lookahead=lookahead, mode=mode)
    return LoopResult(new_state, forecast, decision)
