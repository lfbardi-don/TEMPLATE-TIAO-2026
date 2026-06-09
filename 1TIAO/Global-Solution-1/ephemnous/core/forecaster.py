"""Interface do forecaster e stub de persistencia."""

from __future__ import annotations

from typing import Protocol

from ephemnous.core.models import Forecast, History, NodeState


class Forecaster(Protocol):
    def predict(self, state: NodeState, hist: History, horizon_steps: int, dt_s: float) -> Forecast: ...


class PersistenceForecaster:
    """Repete o valor atual nos proximos passos (baseline de persistencia)."""

    model_version = "persistence-stub"

    def predict(self, state: NodeState, hist: History, horizon_steps: int, dt_s: float) -> Forecast:
        return Forecast(
            horizon_s=int(horizon_steps * dt_s),
            pred_power_w=[state.power_avail_w] * horizon_steps,
            pred_thermal_margin_k=[state.thermal_margin_k] * horizon_steps,
            model_version=self.model_version,
        )
