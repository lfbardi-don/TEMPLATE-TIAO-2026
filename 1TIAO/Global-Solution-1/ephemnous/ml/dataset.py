"""Dataset de treino por rollout determinístico do simulador.

Labels vêm do rollout limpo (futuro conhecido, sem ruído); features vêm de
observações com ruído de sensor (anti-leakage). Um fator de apontamento/atitude
(random walk) dimme o painel além do eclipse orbital: não é nuvem (não há clima
no espaço), modela variação de irradiância por atitude, sombreamento parcial e
degradação. O futuro desse fator não é função da fase, então o forecaster precisa
extrapolar de verdade (skill < 1.0). Split por episódio (em train.py) evita
vazamento treino/validação.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd

from ephemnous.core import physics
from ephemnous.core.models import NodeParams, Telemetry
from ephemnous.ml.features import LAGS, feature_row

HORIZONS = (1, 2, 3, 4, 5)


def generate_episode(seed: int, n_steps: int, base: NodeParams):
    """Roda um episódio e devolve arrays limpos + observados."""
    rng = np.random.default_rng(seed)
    beta = float(rng.choice([0.0, 20.0, 40.0, 60.0]))
    p = replace(base, beta_deg=beta)
    f_ecl = physics.eclipse_fraction(beta, p.altitude_km)

    st = physics.initial_state(p)
    st.t_s = float(rng.uniform(0, p.orbit_period_s))   # fase inicial aleatória
    st.soc_frac = float(rng.uniform(0.4, 1.0))
    st.temp_k = float(rng.uniform(283.0, 303.0))
    st.thermal_margin_k = p.t_max_k - st.temp_k

    keys = ["power_clean", "temp_clean", "margin_clean", "power_obs", "temp_obs",
            "load", "phase", "soc", "in_ecl"]
    a = {k: np.zeros(n_steps) for k in keys}

    pointing, load, block = 1.0, 0.0, 0
    for t in range(n_steps):
        # apontamento/atitude (random walk): incerteza não determinada pela efeméride
        pointing = float(np.clip(pointing * np.exp(rng.normal(0, 0.06)), 0.4, 1.0))
        if block == 0:
            load = float(rng.uniform(0.0, 1.0))
            block = int(rng.integers(2, 6))
        block -= 1

        st = physics.advance(st, Telemetry("train", irradiance_frac=pointing, load_frac=load), p)
        a["power_clean"][t] = st.power_avail_w
        a["temp_clean"][t] = st.temp_k
        a["margin_clean"][t] = st.thermal_margin_k
        a["power_obs"][t] = max(0.0, st.power_avail_w * (1 + rng.normal(0, 0.03)))  # ruído INA219 ~3%
        a["temp_obs"][t] = st.temp_k + rng.normal(0, 0.2)                            # ruído DS18B20 ~0.2K
        a["load"][t] = load
        a["phase"][t] = st.orbit_phase
        a["soc"][t] = st.soc_frac
        a["in_ecl"][t] = 1.0 if st.in_eclipse else 0.0
    return a, beta, f_ecl, p.orbit_period_s


def _regime(phase: float, f_ecl: float) -> str:
    half, d = f_ecl / 2.0, abs(phase - 0.5)
    if d <= half:
        return "eclipse"
    if d <= half + 0.06:
        return "transition"
    return "sun"


def build_dataset(n_episodes: int = 60, n_steps: int = 80, base: NodeParams | None = None,
                  seed0: int = 0) -> pd.DataFrame:
    base = base or NodeParams()
    period_steps = int(round(base.orbit_period_s / base.dt_s))
    maxh = max(HORIZONS)
    rows: list[dict] = []

    for ep in range(n_episodes):
        a, beta, f_ecl, period_s = generate_episode(seed0 + ep, n_steps, base)
        for t in range(LAGS - 1, n_steps - maxh):
            row = feature_row(a["power_obs"], a["temp_obs"], a["load"], a["phase"],
                              a["soc"], t, beta, f_ecl, period_s)
            row["episode"] = ep
            row["regime"] = _regime(a["phase"][t], f_ecl)
            nominal = base.panel_eff * base.s_solar_w_m2 * base.a_panel_m2
            for h in HORIZONS:
                row[f"y_power_h{h}"] = a["power_clean"][t + h]
                row[f"y_margin_h{h}"] = a["margin_clean"][t + h]
                # baseline smart-persistence: mesmo ponto de fase, uma órbita antes
                idx = t + h - period_steps
                if idx >= 0:
                    row[f"b_power_h{h}"] = a["power_obs"][idx]
                    row[f"b_margin_h{h}"] = base.t_max_k - a["temp_obs"][idx]
                else:
                    row[f"b_power_h{h}"] = a["power_obs"][t]
                    row[f"b_margin_h{h}"] = base.t_max_k - a["temp_obs"][t]
                # baseline efeméride: potência nominal da órbita conhecida (apontamento=1, sem
                # incerteza). Skill do ML sobre esta linha = valor do ML na parte incerta.
                row[f"b_power_eph_h{h}"] = nominal * physics.illumination(a["phase"][t + h], f_ecl)
            rows.append(row)

    return pd.DataFrame(rows)
