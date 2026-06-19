"""
Training pipeline — FarmTech Solutions (PARTE 1 + PARTE 2).

For each target (yield, irrigation, fertilizer) it trains and compares:
  - Linear Regression  (linear baseline)
  - Random Forest      (non-linear model)

Evaluates on a held-out test set (80/20 split, no target leakage) using
MAE, MSE, RMSE and R². Saves:
  - src/models/model_<target>.pkl  -> best model (by R²) + metadata;
  - src/models/metrics.csv         -> comparison table of all metrics;
  - docs/figures/*.png             -> actual-vs-predicted and feature importance.

Usage:
    python src/train.py
"""
from __future__ import annotations

import joblib
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")                      # headless backend (writes PNGs)
import matplotlib.pyplot as plt

from sklearn.model_selection import train_test_split
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from config import (
    FEATURES, TARGETS, DATASET_PATH, METRICS_PATH,
    MODELS_DIR, FIGURES_DIR, SEED,
)

BLUE = "#005088"
GREEN = "#11CAA0"


def _load() -> pd.DataFrame:
    if not DATASET_PATH.exists():
        raise FileNotFoundError(
            f"Dataset not found at {DATASET_PATH}. "
            "Run first: python src/generate_dataset.py"
        )
    df = pd.read_csv(DATASET_PATH)
    # Recompute engineered features (defensive, in case of an external CSV).
    df["total_nutrients"] = df["n"] + df["p"] + df["k"]
    df["temp_ph_interaction"] = df["temperature"] * df["ph"]
    return df


def _metrics(y_true, y_pred) -> dict:
    mse = float(mean_squared_error(y_true, y_pred))
    return {
        "MAE": float(mean_absolute_error(y_true, y_pred)),
        "MSE": mse,
        "RMSE": float(np.sqrt(mse)),
        "R2": float(r2_score(y_true, y_pred)),
    }


def _plot_actual_vs_predicted(target, y_true, y_pred, model_name, r2) -> None:
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.scatter(y_true, y_pred, s=10, alpha=0.35, color=BLUE, edgecolors="none")
    lim = [min(y_true.min(), y_pred.min()), max(y_true.max(), y_pred.max())]
    ax.plot(lim, lim, "--", color="#ef4444", linewidth=1.5, label="Previsão perfeita")
    ax.set_xlabel("Valor real")
    ax.set_ylabel("Valor previsto")
    ax.set_title(f"Real × Previsto — {TARGETS[target]}\n{model_name} (R² = {r2:.3f})")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / f"actual_vs_predicted_{target}.png", dpi=110)
    plt.close(fig)


def _plot_importances(target, model) -> None:
    importances = pd.Series(model.feature_importances_, index=FEATURES).sort_values()
    fig, ax = plt.subplots(figsize=(7, 4.5))
    importances.plot.barh(ax=ax, color=GREEN)
    ax.set_title(f"Importância dos atributos — {TARGETS[target]}")
    ax.set_xlabel("Importância relativa")
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / f"importance_{target}.png", dpi=110)
    plt.close(fig)


def train() -> pd.DataFrame:
    df = _load()
    X = df[FEATURES]
    rows = []

    for target in TARGETS:
        y = df[target]
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=SEED
        )

        candidates = {
            "Regressão Linear": LinearRegression(),
            # max_depth + min_samples_leaf regularize the model: they prevent
            # trees from memorizing point by point (better generalization) and
            # shrink the .pkl from ~80 MB to a few MB.
            "Random Forest": RandomForestRegressor(
                n_estimators=150, max_depth=16, min_samples_leaf=5,
                random_state=SEED, n_jobs=-1
            ),
        }

        results = {}
        for name, model in candidates.items():
            model.fit(X_train, y_train)
            y_pred = model.predict(X_test)
            met = _metrics(y_test, y_pred)
            results[name] = {"model": model, "y_pred": y_pred, **met}
            rows.append({
                "target": target, "label": TARGETS[target], "model": name,
                "MAE": round(met["MAE"], 4), "MSE": round(met["MSE"], 4),
                "RMSE": round(met["RMSE"], 4), "R2": round(met["R2"], 4),
            })

        # Best model by R² -> becomes the production model for the target.
        best_name = max(results, key=lambda k: results[k]["R2"])
        best = results[best_name]

        joblib.dump({
            "model": best["model"],
            "features": FEATURES,
            "target": target,
            "label": TARGETS[target],
            "model_name": best_name,
            "metrics": {k: best[k] for k in ("MAE", "MSE", "RMSE", "R2")},
        }, MODELS_DIR / f"model_{target}.pkl")

        _plot_actual_vs_predicted(target, y_test, best["y_pred"], best_name, best["R2"])
        if hasattr(best["model"], "feature_importances_"):
            _plot_importances(target, best["model"])

        print(f"[OK] {target}: best = {best_name} "
              f"(R²={best['R2']:.3f}, RMSE={best['RMSE']:.3f})")

    metrics_df = pd.DataFrame(rows)
    metrics_df.to_csv(METRICS_PATH, index=False)

    print("\n=== COMPARATIVE METRICS (test set) ===")
    print(metrics_df.to_string(index=False))
    print(f"\n[OK] Metrics saved to {METRICS_PATH}")
    return metrics_df


if __name__ == "__main__":
    train()
