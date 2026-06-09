"""Gera as figuras do relatorio em report/ (graficos coloridos, fonte serif)."""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyBboxPatch

from ephemnous.core import physics
from ephemnous.core.models import Forecast, NodeParams, Telemetry
from ephemnous.core.mpc import decide
from ephemnous.infra.ml_forecaster import MLForecaster
from ephemnous.ml.features import LAGS

EMPTY = Forecast(0, [], [])
OUT = Path(__file__).resolve().parent
ROOT = OUT.parent
sys.path.insert(0, str(ROOT / "scripts"))

plt.rcParams.update({
    "font.family": "serif",
    "font.size": 11,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "figure.facecolor": "white",
    "savefig.facecolor": "white",
})


def _box(ax, x, y, w, h, text, color):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.03",
                                fc=color, ec="#333333", lw=1.3))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=9.5)


def _arrow(ax, x1, y1, x2, y2, txt="", off=0.18):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="-|>", lw=1.5, color="#555555"))
    if txt:
        ax.text((x1 + x2) / 2, (y1 + y2) / 2 + off, txt, ha="center", fontsize=8, color="#555555")


def arquitetura():
    fig, ax = plt.subplots(figsize=(9.5, 4.4))
    ax.set_xlim(0, 10); ax.set_ylim(0, 5); ax.axis("off")
    _box(ax, 0.2, 3.1, 2.4, 1.3, "ESP32 (Wokwi)\npot, botao, LED PWM", "#e8f0fe")
    _box(ax, 3.6, 2.9, 2.9, 1.7, "FastAPI\nforecaster (sklearn) + MPC", "#fff3e0")
    _box(ax, 7.4, 3.1, 2.3, 1.3, "PostgreSQL", "#e6f4ea")
    _box(ax, 7.4, 0.5, 2.3, 1.3, "Dashboard\n(Streamlit)", "#f3e8fd")
    _box(ax, 0.2, 0.5, 3.0, 1.3, "Frota simulada\n+ dataset de treino", "#eceff1")
    _box(ax, 3.8, 0.6, 2.5, 1.1, "core/physics\n(uma fisica so)", "#fde7e9")
    _arrow(ax, 2.6, 4.05, 3.6, 4.05, "HTTP POST /telemetria")
    _arrow(ax, 3.6, 3.35, 2.6, 3.35, "comando na resposta", off=-0.28)
    _arrow(ax, 6.5, 3.9, 7.4, 3.9, "grava")
    _arrow(ax, 8.55, 3.1, 8.55, 1.8, "le", off=0.0)
    _arrow(ax, 3.2, 1.2, 3.8, 1.2, "")
    _arrow(ax, 5.05, 1.7, 5.05, 2.9, "")
    _arrow(ax, 1.7, 1.8, 4.6, 2.9, "telemetria simulada", off=0.2)
    plt.tight_layout()
    plt.savefig(OUT / "fig_arquitetura.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("ok fig_arquitetura.png")


def telemetria():
    fc = MLForecaster()
    p = replace(NodeParams(), e_cap_wh=20.0)
    f_ecl = physics.eclipse_fraction(p.beta_deg, p.altitude_km)
    st = physics.initial_state(p)
    st.soc_frac, st.temp_k = 0.6, 293.15
    st.thermal_margin_k = p.t_max_k - st.temp_k

    n = 44
    pw = np.zeros(n); tk = np.zeros(n); ld = np.zeros(n); ph = np.zeros(n); soc = np.zeros(n)
    ecl = np.zeros(n, bool)
    actions = []
    preds: dict[int, list] = {}
    load = 0.0
    for t in range(n):
        st = physics.advance(st, Telemetry("fig", irradiance_frac=1.0, load_frac=load), p)
        pw[t], tk[t], ld[t], ph[t], soc[t] = st.power_avail_w, st.temp_k, load, st.orbit_phase, st.soc_frac
        ecl[t] = st.in_eclipse
        if t >= LAGS - 1:
            fcast = fc.predict_window(pw, tk, ld, ph, soc, t, p.beta_deg, f_ecl,
                                      p.orbit_period_s, p.dt_s, max_h=5)
            preds[t] = [max(0.0, x) for x in fcast.pred_power_w]
            d = decide(st, fcast, p, lookahead=3, mode="mpc")
        else:
            d = decide(st, EMPTY, p, lookahead=0)
        actions.append(d.action)
        load = d.target_pwm / 255.0

    onset = next((t for t in range(1, n) if ecl[t] and not ecl[t - 1]), None)
    snap_t = onset - 2 if onset and onset - 2 in preds else None

    x = np.arange(n)
    fig, axs = plt.subplots(3, 1, figsize=(8.6, 6.6), sharex=True)

    axs[0].plot(x, pw, color="#f5a623", lw=2, label="potencia solar (W)")
    if snap_t is not None:
        xf = np.arange(snap_t, snap_t + len(preds[snap_t]) + 1)
        yf = [pw[snap_t]] + preds[snap_t]
        axs[0].plot(xf, yf, "--", color="#1f6fb2", lw=2, label=f"previsao da IA (em t={snap_t})")
    axs[0].set_ylabel("potencia (W)")
    axs[0].legend(loc="upper right", fontsize=8)

    axs[1].plot(x, tk - 273.15, color="#d0021b", lw=2, label="temperatura (C)")
    axs[1].axhline(p.t_max_k - 273.15, ls=":", color="#888", label="T_max")
    axs[1].set_ylabel("temp (C)")
    axs[1].legend(loc="upper right", fontsize=8)

    axs[2].fill_between(x, soc * 100, color="#7ed321", alpha=0.55)
    axs[2].plot(x, soc * 100, color="#4a7d11", lw=1.2)
    axs[2].set_ylabel("bateria SoC (%)")
    axs[2].set_xlabel("passo (1 passo = 5 min orbitais)")
    axs[2].set_ylim(0, 100)

    for ax in axs:
        for i in range(n):
            if ecl[i]:
                ax.axvspan(i - 0.5, i + 0.5, color="#444", alpha=0.08)
        ax.grid(True, alpha=0.25)
    for i, a in enumerate(actions):
        if a == "checkpoint":
            axs[0].annotate("checkpoint", xy=(i, pw[i]), xytext=(i, pw[i] + 20),
                            fontsize=8, ha="center", color="#1a7a3a",
                            arrowprops=dict(arrowstyle="->", color="#1a7a3a"))
            break

    plt.tight_layout()
    plt.savefig(OUT / "fig_telemetria.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("ok fig_telemetria.png")


def regime():
    import compare_jobs as cj
    fc = MLForecaster()
    seeds = list(range(3000, 3050))
    ecs = [6, 8, 10, 12, 16, 24, 40]
    deltas, cis = [], []
    for ec in ecs:
        base = replace(NodeParams(), e_cap_wh=float(ec))
        ia = np.array([cj.run("ia_mean", s, base, fc)["score"] for s in seeds])
        du = np.array([cj.run("dumb_cons", s, base, fc)["score"] for s in seeds])
        d = ia - du
        deltas.append(d.mean())
        cis.append(1.96 * d.std(ddof=1) / np.sqrt(len(seeds)))
    deltas, cis = np.array(deltas), np.array(cis)

    fig, ax = plt.subplots(figsize=(7.0, 4.0))
    ax.axhline(0, color="#888", lw=1)
    ax.fill_between(ecs, deltas - cis, deltas + cis, alpha=0.2, color="#2e8b57")
    ax.plot(ecs, deltas, marker="o", color="#2e8b57", lw=2, label="vantagem da IA (IC 95%)")
    ax.set_xlabel("capacidade de bateria  e_cap (Wh)  ->  mais folga")
    ax.set_ylabel("delta score (concluidos - 2x perdidos)\nIA - reativo")
    ax.legend()
    ax.grid(True, alpha=0.25)
    plt.tight_layout()
    plt.savefig(OUT / "fig_regime.png", dpi=150, bbox_inches="tight")
    plt.close()
    print("ok fig_regime.png")


if __name__ == "__main__":
    arquitetura()
    telemetria()
    regime()
