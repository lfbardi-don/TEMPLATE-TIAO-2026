"""
Central configuration for the FarmTech project (FASE 4 / CAP 1).

Single source of truth for:
  - file paths (data, models, figures);
  - the FEATURES and TARGETS used by the ML pipeline;
  - the soybean agronomic constants used to build the synthetic dataset;
  - the PostgreSQL connection string (Ir Além 1).

Centralizing these definitions prevents the classic bug of column names
drifting out of sync between the data generator, the trainer and the dashboard.

Note: code/identifiers are in English; user-facing labels (TARGETS values)
stay in Portuguese because the dashboard audience is Brazilian.
"""
from __future__ import annotations

import os
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────
SRC_DIR = Path(__file__).resolve().parent          # .../CAP1/src
ROOT = SRC_DIR.parent                               # .../CAP1
DATA_DIR = ROOT / "data"
MODELS_DIR = SRC_DIR / "models"                     # trained models live under src (FIAP template)
FIGURES_DIR = ROOT / "docs" / "figures"             # plots are visual documentation -> docs

DATASET_PATH = DATA_DIR / "farmtech_soybean_dataset.csv"
METRICS_PATH = MODELS_DIR / "metrics.csv"
SCHEMA_PATH = SRC_DIR / "schema.sql"

for _d in (DATA_DIR, MODELS_DIR, FIGURES_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ── Features and targets (single source of truth) ────────────────────────────
# Sensor variables + two engineered features.
FEATURES = [
    "n", "p", "k",                 # presence of Nitrogen, Phosphorus, Potassium (0/1)
    "ph",                          # soil acidity
    "humidity",                    # soil humidity (%)
    "temperature",                 # soil temperature (°C)
    "pump",                        # irrigation pump active? (0/1)
    "total_nutrients",             # engineered: n + p + k
    "temp_ph_interaction",         # engineered: temperature * ph
]

# Regression targets (technical name -> friendly Portuguese label for the UI).
TARGETS = {
    "yield_ton_ha": "Produtividade estimada (ton/ha)",
    "irrigation_volume_l_m2": "Volume de irrigação (L/m²)",
    "fertilizer_kg_ha": "Fertilizante recomendado (kg/ha)",
}

# ── Soybean (Glycine max) agronomic optima ───────────────────────────────────
# Reference ranges widely cited in agronomic literature, used to build the
# documented relationship between soil/climate/nutrient conditions and yield.
# See README -> "Por que o dataset foi (re)modelado".
OPTIMAL_HUMIDITY = 65.0     # % — ideal soil humidity for soybean
HUMIDITY_SIGMA = 18.0       # tolerance (spread) of the humidity response
OPTIMAL_PH = 6.4            # soybean prefers slightly acidic soil (6.0–6.8)
PH_SIGMA = 0.8
OPTIMAL_TEMP = 27.0         # °C — ideal range 25–30 °C
TEMP_SIGMA = 7.0
MAX_YIELD = 5.8             # ton/ha — yield ceiling under ideal conditions

# Irrigation-need model parameters
TARGET_HUMIDITY_IRRIG = 70.0  # % — soil humidity target to keep
REF_TEMP_IRRIG = 25.0         # °C — above this, evapotranspiration increases

# Fertilization model parameters
FERT_PER_NUTRIENT = 28.0      # kg/ha per missing nutrient
FERT_PER_PH_DEVIATION = 22.0  # kg/ha per unit of pH deviation from the optimum

# Reproducibility seed for the synthetic dataset and the train/test splits.
SEED = 42
N_SAMPLES = 6000


# ── PostgreSQL (Ir Além 1) ───────────────────────────────────────────────────
def postgres_url() -> str:
    """
    Build the SQLAlchemy/psycopg2 connection URL from environment variables
    (loaded from `.env` by src/database.py).

    Accepts a full `DATABASE_URL` or the individual POSTGRES_* variables, with
    defaults matching the project's docker-compose.yml.
    """
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    user = os.getenv("POSTGRES_USER", "farmtech")
    pwd = os.getenv("POSTGRES_PASSWORD", "farmtech")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "farmtech")
    return f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{db}"
