"""Comparativo MPC vs modo burro sobre cenarios identicos (mesma semente, nuvem, eclipse)."""

# Justo por construcao: o burro e o MESMO mpc.decide com lookahead=0 (reativo, cego ao
# futuro). So o cerebro muda. O MPC consome a previsao do forecaster treinado (ML).
#
# Modelo de dados (checkpoint-ou-perde):
# - enquanto roda (load>0), o trabalho fica "em voo" (nao confirmado).
# - checkpoint confirma o trabalho em voo (fica salvo).
# - se a bateria zera com trabalho em voo, esse trabalho e perdido.
# A bateria e apertada de proposito: o drain de um passo e grande, entao o controle
# reativo chega tarde e a previsao ganha (salva antes do eclipse).
#
# Uso:  OMP_NUM_THREADS=1 python scripts/compare.py

from __future__ import annotations

import sys
from dataclasses import replace

import numpy as np

from ephemnous.core import physics
from ephemnous.core.models import Forecast, NodeParams, Telemetry
from ephemnous.core.mpc import decide
from ephemnous.infra.ml_forecaster import MLForecaster
from ephemnous.ml.features import LAGS

EMPTY_FC = Forecast(0, [], [])
N_STEPS = 64
LOOKAHEAD = 3      # MPC olha 3 passos a frente (6 predicts/passo)


def make_env(seed: int, p: NodeParams):
    rng = np.random.default_rng(seed)
    beta = float(rng.choice([0.0, 20.0, 40.0, 60.0]))
    cloud = np.empty(N_STEPS)
    c = 1.0
    for t in range(N_STEPS):
        c = float(np.clip(c * np.exp(rng.normal(0, 0.06)), 0.4, 1.0))
        cloud[t] = c
    init = {
        "t_s": float(rng.uniform(0, p.orbit_period_s)),
        "soc": float(rng.uniform(0.5, 0.9)),
        "temp": float(rng.uniform(285.0, 300.0)),
    }
    return beta, cloud, init


def run_policy(policy: str, seed: int, base: NodeParams, fc: MLForecaster) -> dict:
    beta, cloud, init = make_env(seed, base)
    p = replace(base, beta_deg=beta)
    f_ecl = physics.eclipse_fraction(beta, p.altitude_km)
    obs_rng = np.random.default_rng(seed + 777)  # ruido de sensor, igual para ambas as politicas

    st = physics.initial_state(p)
    st.t_s, st.soc_frac, st.temp_k = init["t_s"], init["soc"], init["temp"]
    st.thermal_margin_k = p.t_max_k - init["temp"]

    pw = np.zeros(N_STEPS); tw = np.zeros(N_STEPS); ld = np.zeros(N_STEPS)
    ph = np.zeros(N_STEPS); soc = np.zeros(N_STEPS)

    lookahead = 0 if policy == "dumb" else LOOKAHEAD
    load = 0.0
    work, lost, inflight = 0.0, 0.0, 0.0
    peak_c, viol, waste = -273.0, 0, 0.0

    for t in range(N_STEPS):
        st = physics.advance(st, Telemetry("x", irradiance_frac=cloud[t], load_frac=load), p)
        pw[t] = max(0.0, st.power_avail_w * (1 + obs_rng.normal(0, 0.03)))
        tw[t] = st.temp_k + obs_rng.normal(0, 0.2)
        ld[t], ph[t], soc[t] = load, st.orbit_phase, st.soc_frac

        # trabalho em voo: compute desta janela, ainda nao salvo
        w_step = load * p.p_comp_max_w * p.dt_s / 3600.0
        work += w_step
        inflight += w_step
        # blackout: bateria zerou com trabalho em voo -> perdido
        if st.soc_frac <= 0.0 and inflight > 0.0:
            lost += inflight
            inflight = 0.0

        peak_c = max(peak_c, st.temp_k - 273.15)
        if st.temp_k > p.t_max_k:
            viol += 1
        p_draw = p.p_base_w + load * p.p_comp_max_w
        if st.soc_frac >= 0.999:
            waste += max(0.0, st.power_avail_w - p_draw) * p.dt_s / 3600.0

        if policy == "mpc" and t >= LAGS - 1:
            fcast = fc.predict_window(pw, tw, ld, ph, soc, t, beta, f_ecl,
                                      p.orbit_period_s, p.dt_s, max_h=LOOKAHEAD)
            d = decide(st, fcast, p, lookahead=lookahead, mode="mpc")
        else:
            d = decide(st, EMPTY_FC, p, lookahead=0, mode="greedy")

        if d.action == "checkpoint":   # salva o trabalho em voo
            inflight = 0.0
        load = d.target_pwm / 255.0

    return {"work": work, "lost": lost, "useful": work - lost,
            "peak_c": peak_c, "viol": viol, "waste": waste}


def main() -> None:
    # bateria apertada: um passo a plena carga drena ~metade da capacidade, entao
    # o reativo chega tarde e a previsao (checkpoint antes do eclipse) ganha.
    base = replace(NodeParams(), e_cap_wh=8.0)
    fc = MLForecaster()
    seeds = list(range(1000, 1050))   # 50 cenarios held-out (treino usou 0..59)

    sums = {pol: {k: 0.0 for k in ["work", "lost", "useful", "viol", "waste"]} for pol in ("dumb", "mpc")}
    peak = {"dumb": -1e9, "mpc": -1e9}

    for i, s in enumerate(seeds, 1):
        for pol in ("dumb", "mpc"):
            m = run_policy(pol, s, base, fc)
            for k in sums[pol]:
                sums[pol][k] += m[k]
            peak[pol] = max(peak[pol], m["peak_c"])
        print(f"  cenario {i}/{len(seeds)} ok", file=sys.stderr, flush=True)
    n = len(seeds)

    print(f"\nComparativo sobre {n} cenarios held-out (medias por cenario)\n")
    rows = [
        ("trab_util(Wh)", "useful", True),
        ("dados_perd(Wh)", "lost", False),
        ("trab_bruto(Wh)", "work", True),
        ("viol_termicas", "viol", False),
        ("pico(C)", "peak_c", False),
        ("desperd(Wh)", "waste", False),
    ]
    print(f"{'metrica':>16} {'BURRO':>10} {'MPC(IA)':>10}   melhor")
    print("-" * 52)
    for label, key, higher_better in rows:
        if key == "peak_c":
            vd, vm = peak["dumb"], peak["mpc"]
        else:
            vd, vm = sums["dumb"][key] / n, sums["mpc"][key] / n
        if abs(vd - vm) < 1e-6:
            best = "="
        elif higher_better:
            best = "MPC" if vm > vd else "BURRO"
        else:
            best = "MPC" if vm < vd else "BURRO"
        print(f"{label:>16} {vd:>10.2f} {vm:>10.2f}   {best}")
    print("\nMesmo cenario, mesma fisica, so muda o cerebro (lookahead 0 vs "
          f"{LOOKAHEAD}). Burro = mesmo codigo, reativo.")


if __name__ == "__main__":
    main()
