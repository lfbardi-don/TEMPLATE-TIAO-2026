"""
Synthetic soybean dataset generator — FarmTech Solutions.

Why synthesize the data?
------------------------
The chapter's original dataset (`../legado_cap1_original/...csv`) is a COMPLETE
FACTORIAL GRID: every combination of (n, p, k, ph, humidity, temperature)
appears exactly once, with no noise. In that grid the variables are
*independent by construction* — the correlation between `humidity` and any other
column is ~0.00. Any regression trying to predict `humidity` from the others
therefore yields a negative R² (worse than predicting the mean): there is no
signal to learn.

Here we generate an agronomically coherent dataset in which the TARGETS are
DOCUMENTED functions of the soil/climate/nutrient conditions, plus realistic
noise. The regression then learns a real response surface and the metrics
(MAE, MSE, RMSE, R²) become real, reproducible and interpretable.

Modeled targets (all with gaussian noise):
  - yield_ton_ha          : multiplicative gaussian response around the optima
                            of humidity, pH, temperature and nutrients
                            (strongly NON-LINEAR -> Random Forest >> Linear).
  - irrigation_volume_l_m2: humidity deficit + evapotranspiration demand
                            (depends on temperature and pump state).
  - fertilizer_kg_ha      : missing nutrients + pH deviation from the optimum.

Usage:
    python src/generate_dataset.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from config import (
    DATASET_PATH, N_SAMPLES, SEED,
    OPTIMAL_HUMIDITY, HUMIDITY_SIGMA, OPTIMAL_PH, PH_SIGMA,
    OPTIMAL_TEMP, TEMP_SIGMA, MAX_YIELD,
    TARGET_HUMIDITY_IRRIG, REF_TEMP_IRRIG,
    FERT_PER_NUTRIENT, FERT_PER_PH_DEVIATION,
)


def _gaussian(x: np.ndarray, mu: float, sigma: float) -> np.ndarray:
    """Normalized gaussian response (1.0 at the optimum, decaying at the tails)."""
    return np.exp(-0.5 * ((x - mu) / sigma) ** 2)


def generate(n: int = N_SAMPLES, seed: int = SEED) -> pd.DataFrame:
    """Generate the synthetic DataFrame with sensor features and management targets."""
    rng = np.random.default_rng(seed)

    # ── Sensor variables (sampled, not a grid) ───────────────────────────────
    humidity = rng.uniform(15, 95, n)              # soil humidity %
    ph = rng.uniform(4.8, 7.8, n)                  # soil acidity
    temperature = rng.uniform(12, 42, n)           # °C
    n_flag = rng.binomial(1, 0.60, n)              # Nitrogen present?
    p_flag = rng.binomial(1, 0.55, n)              # Phosphorus present?
    k_flag = rng.binomial(1, 0.55, n)              # Potassium present?

    # The pump tends to be on when the soil is dry (realistic relationship).
    pump_prob = np.clip(0.85 - humidity / 110.0, 0.05, 0.85)
    pump = (rng.random(n) < pump_prob).astype(int)

    total_nutrients = n_flag + p_flag + k_flag
    temp_ph_interaction = temperature * ph

    # ── TARGET 1: Yield (ton/ha) — multiplicative gaussian surface ────────────
    f_hum = _gaussian(humidity, OPTIMAL_HUMIDITY, HUMIDITY_SIGMA)
    f_ph = _gaussian(ph, OPTIMAL_PH, PH_SIGMA)
    f_temp = _gaussian(temperature, OPTIMAL_TEMP, TEMP_SIGMA)
    # Nutrient adequacy: N weighs less (soybean fixes N via rhizobia); P and K
    # weigh more. Ranges from 0.55 (none) to 1.00 (all present).
    f_nutri = 0.55 + 0.10 * n_flag + 0.175 * p_flag + 0.175 * k_flag
    yield_ton_ha = MAX_YIELD * f_hum * f_ph * f_temp * f_nutri
    yield_ton_ha += rng.normal(0, 0.25, n)         # field noise
    yield_ton_ha = np.clip(yield_ton_ha, 0, None)

    # ── TARGET 2: Irrigation volume (L/m²) ────────────────────────────────────
    deficit = np.clip(TARGET_HUMIDITY_IRRIG - humidity, 0, None)   # water shortage
    et = np.clip(temperature - REF_TEMP_IRRIG, 0, None)            # evapotranspiration
    irrigation_volume = 0.12 * deficit + 0.18 * et + 0.05 * deficit * et / 10.0
    irrigation_volume *= (1 - 0.25 * pump)         # pump already on reduces the extra lamina
    irrigation_volume += rng.normal(0, 0.4, n)
    irrigation_volume = np.clip(irrigation_volume, 0, None)

    # ── TARGET 3: Fertilizer (kg/ha) ──────────────────────────────────────────
    missing = 3 - total_nutrients
    ph_deviation = np.abs(ph - OPTIMAL_PH)
    fertilizer = (FERT_PER_NUTRIENT * missing
                  + FERT_PER_PH_DEVIATION * ph_deviation
                  + 4.0 * missing * ph_deviation)  # non-linear interaction
    fertilizer += rng.normal(0, 5.0, n)
    fertilizer = np.clip(fertilizer, 0, None)

    df = pd.DataFrame({
        "n": n_flag, "p": p_flag, "k": k_flag,
        "ph": ph.round(2),
        "humidity": humidity.round(1),
        "temperature": temperature.round(1),
        "pump": pump,
        "total_nutrients": total_nutrients,
        "temp_ph_interaction": temp_ph_interaction.round(2),
        "yield_ton_ha": yield_ton_ha.round(3),
        "irrigation_volume_l_m2": irrigation_volume.round(3),
        "fertilizer_kg_ha": fertilizer.round(2),
    })

    # ── Categorical ranges (handy for EDA and human reading) ─────────────────
    # Column names are English; the category labels stay in Portuguese because
    # they are rendered as chart tick labels in the dashboard.
    df["humidity_range"] = pd.cut(
        df["humidity"], [-1, 40, 55, 75, 200],
        labels=["critica", "baixa", "adequada", "excesso"])
    df["ph_range"] = pd.cut(
        df["ph"], [-1, 6.0, 6.8, 14],
        labels=["acido", "ideal", "alcalino"])
    df["temperature_range"] = pd.cut(
        df["temperature"], [-1, 18, 32, 100],
        labels=["baixa", "ideal", "estresse"])
    df["source"] = "synthetic_agronomic_soy"
    return df


def main() -> None:
    df = generate()
    df.to_csv(DATASET_PATH, index=False)
    print(f"[OK] Dataset generated: {DATASET_PATH}  ({len(df):,} rows, {df.shape[1]} columns)")
    print("\n--- First rows ---")
    print(df.head().to_string(index=False))
    print("\n--- Target statistics ---")
    print(df[["yield_ton_ha", "irrigation_volume_l_m2",
              "fertilizer_kg_ha"]].describe().round(2).to_string())


if __name__ == "__main__":
    main()
