"""Admissão de jobs não-interrompíveis: ablação de 4 vias.

Job = D passos a plena carga; uma vez iniciado, ou termina ou (bateria zerou no meio)
e perdido. A decisão de INICIAR e a mesma para todas as políticas: simula o SoC ao longo
dos D passos com a geração prevista e só admite se a bateria não zera no caminho. Só muda
a fonte da previsão:

  dumb_mean : persiste a geração atual (otimista quando esta sol agora)
  dumb_cons : persiste a geração atual x 0.6 (reativo conservador, sem ML)
  ia_mean   : previsão média do forecaster ML
  ia_p10    : previsão P10 do forecaster ML (pior caso plausível, ML + aversão a risco)

Separa dois efeitos: ML (ia_p10 vs dumb_cons) e aversão a risco (ia_p10 vs ia_mean).
Métrica líquida: score = concluídos - LAMBDA*perdidos. LAMBDA=2 congelado antes de rodar.
IC pareado (mesma semente roda todas as políticas) em 2 regimes de bateria.
Uso:  OMP_NUM_THREADS=1 python scripts/compare_jobs.py
"""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

from ephemnous.core import physics
from ephemnous.core.models import NodeParams, Telemetry
from ephemnous.infra.ml_forecaster import MLForecaster

N = 64
D = 4          # duração do job (passos)
LAMBDA = 2.0   # custo de um job perdido, em jobs concluídos equivalentes (congelado)
POLICIES = ("dumb_mean", "dumb_cons", "ia_mean", "ia_p10")


def make_env(seed: int, p: NodeParams):
    rng = np.random.default_rng(seed)
    beta = float(rng.choice([0.0, 20.0, 40.0, 60.0]))
    cloud = np.empty(N)
    c = 1.0
    for t in range(N):
        c = float(np.clip(c * np.exp(rng.normal(0, 0.06)), 0.4, 1.0))
        cloud[t] = c
    init = {"t_s": float(rng.uniform(0, p.orbit_period_s)),
            "soc": float(rng.uniform(0.5, 0.9)),
            "temp": float(rng.uniform(285.0, 300.0))}
    return beta, cloud, init


def survives(soc0: float, e_cap_j: float, pred_gen: list[float], draw_w: float, dt: float) -> bool:
    """Simula o SoC ao longo do job com a geração prevista; True se a bateria nunca zera."""
    e = soc0 * e_cap_j
    for g in pred_gen:
        e += (max(0.0, g) - draw_w) * dt
        if e <= 0.0:
            return False
        e = min(e, e_cap_j)
    return True


def run(policy: str, seed: int, base: NodeParams, fc: MLForecaster) -> dict:
    beta, cloud, init = make_env(seed, base)
    p = replace(base, beta_deg=beta)
    f_ecl = physics.eclipse_fraction(beta, p.altitude_km)
    obs_rng = np.random.default_rng(seed + 777)   # ruído de sensor, casa com o treino, igual p/ todos
    e_cap_j = p.e_cap_wh * 3600.0
    draw_w = p.p_comp_max_w + p.p_base_w

    st = physics.initial_state(p)
    st.t_s, st.soc_frac, st.temp_k = init["t_s"], init["soc"], init["temp"]
    st.thermal_margin_k = p.t_max_k - st.temp_k

    pw = np.zeros(N); tw = np.zeros(N); ld = np.zeros(N); ph = np.zeros(N); soc = np.zeros(N)
    job_active, steps_left = False, 0
    completed, lost, started = 0, 0, 0

    for t in range(N):
        load = 1.0 if job_active else 0.0
        st = physics.advance(st, Telemetry("job", irradiance_frac=cloud[t], load_frac=load), p)
        pw[t] = max(0.0, st.power_avail_w * (1 + obs_rng.normal(0, 0.03)))
        tw[t] = st.temp_k + obs_rng.normal(0, 0.2)
        ld[t], ph[t], soc[t] = load, st.orbit_phase, st.soc_frac

        if job_active:
            if st.soc_frac <= 0.0:
                lost += 1
                job_active, steps_left = False, 0
            else:
                steps_left -= 1
                if steps_left <= 0:
                    completed += 1
                    job_active = False
        elif t >= 3:
            if policy == "ia_p10":
                pred = fc.predict_power_p10(pw, tw, ld, ph, soc, t, beta, f_ecl, p.orbit_period_s, D)
            elif policy == "ia_mean":
                pred = fc.predict_window(pw, tw, ld, ph, soc, t, beta, f_ecl,
                                         p.orbit_period_s, p.dt_s, max_h=D).pred_power_w
            else:
                g = pw[t] * (0.6 if policy == "dumb_cons" else 1.0)
                pred = [g] * D
            if survives(st.soc_frac, e_cap_j, pred, draw_w, p.dt_s):
                job_active, steps_left, started = True, D, started + 1

    score = completed - LAMBDA * lost
    return {"completed": completed, "lost": lost, "started": started, "score": score}


def regime(e_cap_wh: float, seeds, fc) -> None:
    base = replace(NodeParams(), e_cap_wh=e_cap_wh)
    n = len(seeds)
    per = {pol: {"completed": [], "lost": [], "score": []} for pol in POLICIES}
    for s in seeds:
        for pol in POLICIES:
            m = run(pol, s, base, fc)
            for k in ("completed", "lost", "score"):
                per[pol][k].append(m[k])

    print(f"\n========== bateria e_cap = {e_cap_wh:.0f} Wh  ({n} sementes) ==========")
    print(f"{'política':>11} {'concluídos':>11} {'perdidos':>9} {'score(c-2p)':>12}")
    for pol in POLICIES:
        c = np.mean(per[pol]["completed"]); l = np.mean(per[pol]["lost"]); s = np.mean(per[pol]["score"])
        print(f"{pol:>11} {c:>11.2f} {l:>9.2f} {s:>12.2f}")

    def paired(a: str, b: str) -> str:
        d = np.array(per[a]["score"]) - np.array(per[b]["score"])
        mean, sd = d.mean(), d.std(ddof=1)
        ci = 1.96 * sd / np.sqrt(n)
        verdict = "ROBUSTO (IC>0)" if mean - ci > 0 else ("empate (IC cruza 0)" if mean + ci > 0 else "PIOR")
        return f"delta_score({a}-{b}) = {mean:+.2f} +- {ci:.2f}  -> {verdict}"

    print("  " + paired("ia_mean", "dumb_cons") + "   [valor do ML vs reativo conservador]")
    print("  " + paired("ia_mean", "dumb_mean") + "   [valor do ML vs reativo otimista]")
    print("  " + paired("ia_p10", "ia_mean") + "   [ablação: P10 = aversão a risco extrema]")


def regime_curve(fc: MLForecaster) -> None:
    """Vantagem líquida da IA vs dureza energética (e_cap)."""
    seeds = list(range(3000, 3050))
    print("\n===== CURVA DE REGIME: delta_score(IA-média - burro) vs capacidade de bateria =====")
    print(f"{'e_cap_Wh':>9} {'IA':>7} {'burro':>7} {'delta_score':>8} {'+-IC95':>7}  veredito")
    for ec in (6, 8, 10, 12, 16, 24, 40):
        base = replace(NodeParams(), e_cap_wh=float(ec))
        ia = np.array([run("ia_mean", s, base, fc)["score"] for s in seeds])
        du = np.array([run("dumb_cons", s, base, fc)["score"] for s in seeds])
        d = ia - du
        ci = 1.96 * d.std(ddof=1) / np.sqrt(len(seeds))
        verd = "IA vence" if d.mean() - ci > 0 else "empate"
        print(f"{ec:>9} {ia.mean():>7.2f} {du.mean():>7.2f} {d.mean():>+8.2f} {ci:>7.2f}  {verd}")
    print("Leitura: vantagem honesta concentrada no regime energia-crítico; some com folga.")


def save_regime_png(fc: MLForecaster, path: str = "data/regime_curve.png") -> None:
    """Salva a curva de regime como PNG (para slides)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    seeds = list(range(3000, 3050))
    ecs = [6, 8, 10, 12, 16, 24, 40]
    deltas, cis = [], []
    for ec in ecs:
        base = replace(NodeParams(), e_cap_wh=float(ec))
        ia = np.array([run("ia_mean", s, base, fc)["score"] for s in seeds])
        du = np.array([run("dumb_cons", s, base, fc)["score"] for s in seeds])
        d = ia - du
        deltas.append(d.mean())
        cis.append(1.96 * d.std(ddof=1) / np.sqrt(len(seeds)))

    deltas, cis = np.array(deltas), np.array(cis)
    plt.figure(figsize=(7.2, 4.2))
    plt.axhline(0, color="#888", lw=1)
    plt.fill_between(ecs, deltas - cis, deltas + cis, alpha=0.2, color="#2e8b57")
    plt.plot(ecs, deltas, marker="o", color="#2e8b57", lw=2, label="vantagem da IA (IC 95%)")
    plt.xlabel("Capacidade de bateria  e_cap (Wh)  ->  mais folga")
    plt.ylabel("delta score  (concluidos - 2x perdidos)\nIA - reativo")
    plt.title("ephemnous: onde a previsão importa\n(vantagem honesta concentrada no regime energia-crítico)")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    Path("data").mkdir(exist_ok=True)
    plt.savefig(path, dpi=130)
    print(f"PNG salvo em {path}")


def main() -> None:
    fc = MLForecaster()
    if len(sys.argv) > 1 and sys.argv[1] == "plot":
        save_regime_png(fc)
        return
    regime(8.0, list(range(3000, 3050)), fc)   # ablação detalhada de 4 vias no regime crítico
    regime_curve(fc)


if __name__ == "__main__":
    main()
