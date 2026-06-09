"""Extração de features para o forecaster."""

# Anti-leakage: toda feature usa só informação em t ou antes (lags, janelas, fase
# atual), nunca t+h. A fase (efeméride) é conhecida e é honesto usá-la; o futuro
# fica não-trivial por causa do fator ambiental estocástico (nuvem/atitude), que
# não é função da fase. A mesma função roda no treino e na inferência (sem skew).

from __future__ import annotations

import numpy as np

LAGS = 4   # power[t..t-3]
WIN = 5    # janela das estatísticas móveis


def time_to_next_eclipse_s(phase: float, f_ecl: float, period_s: float) -> float:
    """Segundos até o próximo eclipse (efeméride conhecida)."""
    if f_ecl <= 0:
        return period_s
    start, end = 0.5 - f_ecl / 2.0, 0.5 + f_ecl / 2.0
    if phase < start:
        return (start - phase) * period_s
    if phase <= end:
        return 0.0
    return (1.0 + start - phase) * period_s


def feature_row(
    power_obs: np.ndarray,
    temp_obs: np.ndarray,
    load: np.ndarray,
    phase: np.ndarray,
    soc: np.ndarray,
    t: int,
    beta: float,
    f_ecl: float,
    period_s: float,
) -> dict:
    feats: dict[str, float] = {}
    for j in range(LAGS):
        feats[f"power_lag{j}"] = float(power_obs[t - j])
        feats[f"temp_lag{j}"] = float(temp_obs[t - j])
        feats[f"load_lag{j}"] = float(load[t - j])

    w0 = max(0, t - WIN + 1)
    pw, tw = power_obs[w0 : t + 1], temp_obs[w0 : t + 1]
    feats["power_mean"] = float(pw.mean())
    feats["power_std"] = float(pw.std())
    feats["temp_mean"] = float(tw.mean())
    feats["temp_std"] = float(tw.std())
    feats["power_slope"] = float(pw[-1] - pw[0])
    feats["temp_slope"] = float(tw[-1] - tw[0])

    ph = float(phase[t])
    feats["sin_phase"] = float(np.sin(2 * np.pi * ph))
    feats["cos_phase"] = float(np.cos(2 * np.pi * ph))
    feats["ttne_s"] = time_to_next_eclipse_s(ph, f_ecl, period_s)
    feats["beta"] = float(beta)
    feats["soc"] = float(soc[t])
    feats["load_now"] = float(load[t])
    return feats


def feature_names() -> list[str]:
    """Ordem canônica das colunas de feature (treino == inferência)."""
    cols: list[str] = []
    for j in range(LAGS):
        cols += [f"power_lag{j}", f"temp_lag{j}", f"load_lag{j}"]
    cols += [
        "power_mean", "power_std", "temp_mean", "temp_std",
        "power_slope", "temp_slope", "sin_phase", "cos_phase",
        "ttne_s", "beta", "soc", "load_now",
    ]
    return cols
