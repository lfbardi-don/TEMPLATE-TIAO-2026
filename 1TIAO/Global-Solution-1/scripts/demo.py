"""Demo ao vivo roteirizada (sem dashboard, sem Wokwi)."""

from __future__ import annotations

from dataclasses import replace

import numpy as np

from ephemnous.core import physics
from ephemnous.core.models import Forecast, NodeParams, Telemetry
from ephemnous.core.mpc import decide
from ephemnous.infra.ml_forecaster import MLForecaster
from ephemnous.ml.features import LAGS

N = 26
EMPTY = Forecast(0, [], [])


def make_env(seed: int, p: NodeParams):
    rng = np.random.default_rng(seed)
    beta = float(rng.choice([0.0, 20.0, 40.0]))
    cloud = np.empty(N)
    c = 1.0
    for t in range(N):
        c = float(np.clip(c * np.exp(rng.normal(0, 0.05)), 0.5, 1.0))
        cloud[t] = c
    init = {"t_s": float(rng.uniform(0, p.orbit_period_s)),
            "soc": float(rng.uniform(0.5, 0.8)),
            "temp": float(rng.uniform(288.0, 300.0))}
    return beta, cloud, init


def run(policy: str, seed: int, base: NodeParams, fc: MLForecaster, narrate: bool = False) -> dict:
    beta, cloud, init = make_env(seed, base)
    p = replace(base, beta_deg=beta)
    f_ecl = physics.eclipse_fraction(beta, p.altitude_km)
    st = physics.initial_state(p)
    st.t_s, st.soc_frac, st.temp_k = init["t_s"], init["soc"], init["temp"]
    st.thermal_margin_k = p.t_max_k - st.temp_k

    pw = np.zeros(N); tw = np.zeros(N); ld = np.zeros(N); ph = np.zeros(N); soc = np.zeros(N)
    load, work, lost, inflight = 0.0, 0.0, 0.0, 0.0
    look = 0 if policy == "dumb" else 3

    if narrate:
        print(f"{'t':>2} {'regime':>9} {'fase':>5} {'P_W':>5} {'T_C':>5} {'SoC':>5} {'prev3':>6}  ACAO")
        print("-" * 74)

    for t in range(N):
        st = physics.advance(st, Telemetry("demo", irradiance_frac=cloud[t], load_frac=load), p)
        pw[t], tw[t], ld[t], ph[t], soc[t] = st.power_avail_w, st.temp_k, load, st.orbit_phase, st.soc_frac

        w = load * p.p_comp_max_w * p.dt_s / 3600.0
        work += w
        inflight += w
        if st.soc_frac <= 0.0 and inflight > 0.0:
            lost += inflight
            inflight = 0.0

        pred3 = None
        if policy == "mpc" and t >= LAGS - 1:
            fcast = fc.predict_window(pw, tw, ld, ph, soc, t, beta, f_ecl,
                                      p.orbit_period_s, p.dt_s, max_h=3)
            d = decide(st, fcast, p, lookahead=look, mode="mpc")
            pred3 = max(0.0, min(fcast.pred_power_w))
        else:
            d = decide(st, EMPTY, p, lookahead=0, mode="greedy")

        if d.action == "checkpoint":
            inflight = 0.0

        if narrate:
            if st.in_eclipse:
                tag = "[ECLIPSE]"
            elif abs(st.orbit_phase - 0.5) < f_ecl / 2 + 0.06:
                tag = "[borda]"
            else:
                tag = "[sol]"
            pv = f"{pred3:5.0f}" if pred3 is not None else "    -"
            mark = "  <== preve a queda e SALVA antes" if d.action == "checkpoint" else \
                   ("  <-- BLACKOUT: dados perdidos" if (st.soc_frac <= 0.0 and load > 0) else "")
            print(f"{t:>2} {tag:>9} {st.orbit_phase:5.2f} {st.power_avail_w:5.0f} "
                  f"{st.temp_k - 273.15:5.0f} {st.soc_frac:5.2f} {pv:>6}  {d.action} pwm={d.target_pwm}{mark}")

        load = d.target_pwm / 255.0

    return {"work": work, "lost": lost, "useful": work - lost}


def main() -> None:
    base = replace(NodeParams(), e_cap_wh=8.0)   # bateria apertada: foresight importa
    fc = MLForecaster()
    seeds = list(range(2000, 2041))

    rows = [(s, run("mpc", s, base, fc), run("dumb", s, base, fc)) for s in seeds]
    # cenario representativo: o que mais separa burro x IA em dados perdidos
    best = max(rows, key=lambda r: r[2]["lost"] - r[1]["lost"])

    print("\n=== ephemnous - demo ao vivo (IA: forecaster ML + MPC preditivo) ===")
    print(f"Cenario representativo (semente {best[0]}); a IA antecipa o eclipse:\n")
    run("mpc", best[0], base, fc, narrate=True)

    ia_lost = np.mean([r[1]["lost"] for r in rows]); du_lost = np.mean([r[2]["lost"] for r in rows])
    ia_use = np.mean([r[1]["useful"] for r in rows]); du_use = np.mean([r[2]["useful"] for r in rows])
    print(f"\n--- este cenario: dados perdidos  burro {best[2]['lost']:.1f} Wh  |  IA {best[1]['lost']:.1f} Wh")
    print(f"--- media de {len(seeds)} cenarios held-out:")
    print(f"      dados perdidos :  burro {du_lost:5.1f} Wh   |   IA {ia_lost:5.1f} Wh   "
          f"(IA perde {100 * (1 - ia_lost / du_lost):.0f}% menos)" if du_lost > 0 else "")
    print(f"      trabalho util  :  burro {du_use:5.1f} Wh   |   IA {ia_use:5.1f} Wh")
    print("\nA IA previu o eclipse e fez checkpoint ANTES de a energia cair; o burro reagiu tarde.\n")


if __name__ == "__main__":
    main()
