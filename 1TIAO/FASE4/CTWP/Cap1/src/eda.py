"""
Exploratory Data Analysis (EDA) — FarmTech Solutions.

Generates the figures consumed by the dashboard:
  - docs/figures/correlation.png         -> correlation matrix (features + targets);
  - docs/figures/distributions.png       -> sensor variable distributions;
  - docs/figures/yield_by_range.png      -> mean yield by pH, humidity and
                                            temperature range.

Figure titles/labels are kept in Portuguese (presentation for the dashboard).

Usage:
    python src/eda.py
"""
from __future__ import annotations

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns

from config import DATASET_PATH, FIGURES_DIR, TARGETS

NUMERIC_COLS = [
    "n", "p", "k", "ph", "humidity", "temperature", "pump",
    "total_nutrients", "temp_ph_interaction",
    "yield_ton_ha", "irrigation_volume_l_m2", "fertilizer_kg_ha",
]


def _load() -> pd.DataFrame:
    if not DATASET_PATH.exists():
        raise FileNotFoundError(
            f"Dataset not found at {DATASET_PATH}. "
            "Run first: python src/generate_dataset.py"
        )
    return pd.read_csv(DATASET_PATH)


def correlation_matrix(df: pd.DataFrame) -> None:
    corr = df[NUMERIC_COLS].corr()
    fig, ax = plt.subplots(figsize=(11, 9))
    sns.heatmap(corr, annot=True, cmap="coolwarm", fmt=".2f",
                linewidths=0.5, ax=ax, vmin=-1, vmax=1)
    ax.set_title("Matriz de Correlação — Sensores e Alvos de Manejo")
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "correlation.png", dpi=110)
    plt.close(fig)


def distributions(df: pd.DataFrame) -> None:
    cols = ["humidity", "ph", "temperature", "yield_ton_ha"]
    fig, axes = plt.subplots(2, 2, figsize=(11, 7))
    for ax, col in zip(axes.ravel(), cols):
        sns.histplot(df[col], kde=True, ax=ax, color="#005088")
        ax.set_title(f"Distribuição — {col}")
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "distributions.png", dpi=110)
    plt.close(fig)


def yield_by_range(df: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(14, 4))
    for ax, range_col, title in [
        (axes[0], "humidity_range", "Umidade"),
        (axes[1], "ph_range", "pH"),
        (axes[2], "temperature_range", "Temperatura"),
    ]:
        mean = df.groupby(range_col, observed=True)["yield_ton_ha"].mean()
        mean.plot.bar(ax=ax, color="#11CAA0")
        ax.set_title(f"Produtividade média por faixa de {title}")
        ax.set_ylabel("ton/ha")
        ax.set_xlabel("")
        ax.tick_params(axis="x", rotation=20)
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "yield_by_range.png", dpi=110)
    plt.close(fig)


def main() -> None:
    df = _load()
    correlation_matrix(df)
    distributions(df)
    yield_by_range(df)
    print(f"[OK] EDA figures saved to {FIGURES_DIR}/")
    print("\nTarget correlation with features (top):")
    corr = df[NUMERIC_COLS].corr()
    for target in TARGETS:
        s = corr[target].drop(labels=list(TARGETS)).abs().sort_values(ascending=False)
        print(f"  {target}: " + ", ".join(f"{i}={v:.2f}" for i, v in s.head(3).items()))


if __name__ == "__main__":
    main()
