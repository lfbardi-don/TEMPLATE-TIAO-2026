"""Treina o forecaster e reporta skill vs smart-persistence."""

from __future__ import annotations

import json
import math
import pickle
from pathlib import Path

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor

from ephemnous.core.models import NodeParams
from ephemnous.ml.dataset import HORIZONS, build_dataset
from ephemnous.ml.features import feature_names

MODELS_DIR = Path(__file__).resolve().parent.parent / "ephemnous" / "ml" / "models"
REGIMES = ("sun", "transition", "eclipse")


def rmse(pred: np.ndarray, true: np.ndarray) -> float:
    return float(np.sqrt(np.mean((np.asarray(pred) - np.asarray(true)) ** 2)))


def skill(rmse_model: float, rmse_base: float) -> float:
    return 1.0 - rmse_model / rmse_base if rmse_base > 1e-9 else 0.0


def main() -> None:
    base = NodeParams()
    print("Gerando dataset (60 episodios x 80 passos)...")
    df = build_dataset(n_episodes=60, n_steps=80, base=base)
    feat_cols = feature_names()

    episodes = np.sort(df["episode"].unique())
    n_val = max(1, len(episodes) // 4)
    val_eps = set(episodes[-n_val:].tolist())
    tr = df[~df["episode"].isin(val_eps)]
    va = df[df["episode"].isin(val_eps)]
    print(f"Treino: {len(tr)} linhas ({len(episodes) - n_val} ep) | "
          f"Validacao: {len(va)} linhas ({n_val} ep)\n")

    Xtr = tr[feat_cols].to_numpy()
    Xva = va[feat_cols].to_numpy()
    models: dict[tuple[str, int], HistGradientBoostingRegressor] = {}
    metrics: list[dict] = []

    def _nn(x: float):  # nan -> None para o JSON
        return None if (isinstance(x, float) and math.isnan(x)) else round(float(x), 3)

    hdr = (f"{'alvo':>7} {'h':>2} {'rmse_mdl':>9} {'rmse_base':>9} {'skill':>6} "
           f"{'sk_efem':>7} {'sun':>6} {'transi':>7} {'eclip':>6} {'gap_tr':>7}")
    print(hdr)
    print("-" * len(hdr))

    for target in ("power", "margin"):
        for h in HORIZONS:
            ycol, bcol = f"y_{target}_h{h}", f"b_{target}_h{h}"
            m = HistGradientBoostingRegressor(
                max_depth=3, learning_rate=0.05, max_iter=300, l2_regularization=1.0,
                random_state=0,
            )
            m.fit(Xtr, tr[ycol].to_numpy())
            models[(target, h)] = m

            pred_va = m.predict(Xva)
            r_mdl = rmse(pred_va, va[ycol].to_numpy())
            r_base = rmse(va[bcol].to_numpy(), va[ycol].to_numpy())
            sk = skill(r_mdl, r_base)

            # skill vs efemeride (so power): ganho do ML acima da fisica orbital conhecida
            if target == "power":
                r_eph = rmse(va[f"b_power_eph_h{h}"].to_numpy(), va[ycol].to_numpy())
                sk_eph = skill(r_mdl, r_eph)
            else:
                sk_eph = float("nan")

            sk_reg = {}
            for reg in REGIMES:
                mask = (va["regime"] == reg).to_numpy()
                if mask.sum() >= 5:
                    rm = rmse(pred_va[mask], va[ycol].to_numpy()[mask])
                    rb = rmse(va[bcol].to_numpy()[mask], va[ycol].to_numpy()[mask])
                    sk_reg[reg] = skill(rm, rb)
                else:
                    sk_reg[reg] = float("nan")

            # gap de overfit: rmse treino vs val, normalizado pelo base
            r_tr = rmse(m.predict(Xtr), tr[ycol].to_numpy())
            gap = (r_mdl - r_tr) / r_base if r_base > 1e-9 else 0.0

            print(f"{target:>7} {h:>2} {r_mdl:>9.2f} {r_base:>9.2f} {sk:>6.2f} "
                  f"{sk_eph:>7.2f} {sk_reg['sun']:>6.2f} {sk_reg['transition']:>7.2f} "
                  f"{sk_reg['eclipse']:>6.2f} {gap:>7.2f}")

            metrics.append({
                "target": target, "h": h, "rmse_model": _nn(r_mdl), "rmse_base": _nn(r_base),
                "skill": _nn(sk), "skill_eph": _nn(sk_eph), "skill_sun": _nn(sk_reg["sun"]),
                "skill_transition": _nn(sk_reg["transition"]), "skill_eclipse": _nn(sk_reg["eclipse"]),
                "gap_tr": _nn(gap),
            })

    # Modelos de quantil P10 (pior caso plausivel) de power: a previsao media e otimista,
    # usar P10 faz a IA nao admitir jobs no pior momento (admissao ciente de risco).
    for h in HORIZONS:
        mq = HistGradientBoostingRegressor(
            loss="quantile", quantile=0.1, max_depth=3, learning_rate=0.05,
            max_iter=300, l2_regularization=1.0, random_state=0,
        )
        mq.fit(Xtr, tr[f"y_power_h{h}"].to_numpy())
        models[("power_p10", h)] = mq
    print("\n+ modelos P10 (quantil 0.1) de power para admissao ciente de risco.")

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    out = MODELS_DIR / "forecaster.pkl"
    with open(out, "wb") as f:
        pickle.dump({"models": models, "feature_cols": feat_cols, "horizons": list(HORIZONS)}, f)
    (MODELS_DIR / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(f"\nModelo salvo em {out} | metricas em {MODELS_DIR / 'metrics.json'}")
    print("Leitura: skill>0 = bate a persistencia; skill~1.0 = suspeitar de leakage; "
          "gap_tr pequeno = sem overfit forte.")


if __name__ == "__main__":
    main()
