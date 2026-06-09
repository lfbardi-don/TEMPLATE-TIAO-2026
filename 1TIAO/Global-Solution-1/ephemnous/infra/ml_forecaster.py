"""Carrega o modelo treinado e produz uma Forecast a partir da janela de observacoes."""

from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np

from ephemnous.core.models import Forecast, History, NodeState
from ephemnous.ml.features import LAGS, feature_row

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "ml" / "models" / "forecaster.pkl"


class MLForecaster:
    model_version = "hgb"

    def __init__(self, path: Path = DEFAULT_PATH):
        with open(path, "rb") as f:
            d = pickle.load(f)
        self.models = d["models"]
        self.feature_cols = d["feature_cols"]
        self.horizons = list(d["horizons"])

    def predict(self, state: NodeState, hist: History, horizon_steps: int, dt_s: float) -> Forecast:
        n = len(hist.power)
        if n < LAGS:  # historico insuficiente -> persistencia (warmup)
            steps = len(self.horizons)
            return Forecast(
                horizon_s=int(max(self.horizons) * dt_s),
                pred_power_w=[state.power_avail_w] * steps,
                pred_thermal_margin_k=[state.thermal_margin_k] * steps,
                model_version="persistence-warmup",
            )
        return self.predict_window(
            np.asarray(hist.power), np.asarray(hist.temp), np.asarray(hist.load),
            np.asarray(hist.phase), np.asarray(hist.soc), n - 1,
            hist.beta, hist.f_ecl, hist.period_s, dt_s,
        )

    def predict_window(
        self,
        power_obs: np.ndarray,
        temp_obs: np.ndarray,
        load: np.ndarray,
        phase: np.ndarray,
        soc: np.ndarray,
        t: int,
        beta: float,
        f_ecl: float,
        period_s: float,
        dt_s: float,
        max_h: int | None = None,
    ) -> Forecast:
        hs = [h for h in self.horizons if (max_h is None or h <= max_h)]
        feats = feature_row(power_obs, temp_obs, load, phase, soc, t, beta, f_ecl, period_s)
        x = np.array([[feats[c] for c in self.feature_cols]])
        powers = [float(self.models[("power", h)].predict(x)[0]) for h in hs]
        margins = [float(self.models[("margin", h)].predict(x)[0]) for h in hs]
        return Forecast(
            horizon_s=int(max(hs) * dt_s),
            pred_power_w=powers,
            pred_thermal_margin_k=margins,
            model_version=self.model_version,
        )

    def predict_power_p10(
        self,
        power_obs: np.ndarray,
        temp_obs: np.ndarray,
        load: np.ndarray,
        phase: np.ndarray,
        soc: np.ndarray,
        t: int,
        beta: float,
        f_ecl: float,
        period_s: float,
        max_h: int,
    ) -> list[float]:
        """Power no quantil P10 (pior caso plausivel) por horizonte, para admissao ciente de risco."""
        hs = [h for h in self.horizons if h <= max_h]
        feats = feature_row(power_obs, temp_obs, load, phase, soc, t, beta, f_ecl, period_s)
        x = np.array([[feats[c] for c in self.feature_cols]])
        return [float(self.models[("power_p10", h)].predict(x)[0]) for h in hs]
