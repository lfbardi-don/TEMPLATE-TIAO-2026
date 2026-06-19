"""
Central configuration for the seed-classification project (FASE 4 / CAP 3).

Single source of truth for:
  - file paths (raw/clean data, models, figures);
  - the column names, FEATURES and TARGET used across the pipeline;
  - the wheat-variety class mapping and Portuguese display labels;
  - the candidate classifiers and their hyperparameter grids (Grid Search).

Centralizing these definitions prevents the classic bug of column names or
model settings drifting out of sync between the data loader, the notebook and
any auxiliary script.

Note: code/identifiers are in English; user-facing labels (class names and
feature labels used in the plots) stay in Portuguese because the audience of
the analysis is Brazilian (a small agricultural cooperative).
"""
from __future__ import annotations

from pathlib import Path

from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.neighbors import KNeighborsClassifier
from sklearn.svm import SVC
from sklearn.ensemble import RandomForestClassifier
from sklearn.naive_bayes import GaussianNB
from sklearn.linear_model import LogisticRegression

# ── Paths ────────────────────────────────────────────────────────────────────
SRC_DIR = Path(__file__).resolve().parent          # .../CAP3/src
ROOT = SRC_DIR.parent                               # .../CAP3
DATA_DIR = ROOT / "data"
MODELS_DIR = SRC_DIR / "models"                     # trained artifacts live under src (FIAP template)
FIGURES_DIR = ROOT / "docs" / "figures"             # plots are visual documentation -> docs

RAW_DATASET_PATH = DATA_DIR / "seeds_dataset.txt"   # original UCI file (whitespace separated)
CLEAN_DATASET_PATH = DATA_DIR / "seeds_clean.csv"   # tidy CSV produced by src/data.py

METRICS_BASELINE_PATH = MODELS_DIR / "metrics_baseline.csv"
METRICS_TUNED_PATH = MODELS_DIR / "metrics_tuned.csv"
BEST_PARAMS_PATH = MODELS_DIR / "best_params.json"

for _d in (DATA_DIR, MODELS_DIR, FIGURES_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ── Columns, features and target (single source of truth) ────────────────────
# The UCI "Seeds" file has 8 whitespace-separated columns, no header.
COLUMN_NAMES = [
    "area",            # area A of the grain
    "perimeter",       # perimeter P of the grain contour
    "compactness",     # C = 4*pi*A / P^2
    "kernel_length",   # length of the kernel (main axis of the equivalent ellipse)
    "kernel_width",    # width of the kernel (secondary axis)
    "asymmetry",       # asymmetry coefficient
    "groove_length",   # length of the kernel groove
    "variety",         # class label: 1, 2 or 3 (see CLASS_MAP)
]

FEATURES = COLUMN_NAMES[:-1]   # the 7 physical measurements
TARGET = "variety"             # integer class column
TARGET_NAME = "variety_name"   # human-readable class column (added by the loader)

# Class label (integer in the file) -> wheat variety name.
CLASS_MAP = {1: "Kama", 2: "Rosa", 3: "Canadian"}

# Portuguese labels for plots/reporting (presentation layer only).
FEATURE_LABELS_PT = {
    "area": "Área",
    "perimeter": "Perímetro",
    "compactness": "Compacidade",
    "kernel_length": "Comprimento do núcleo",
    "kernel_width": "Largura do núcleo",
    "asymmetry": "Coef. de assimetria",
    "groove_length": "Comprimento do sulco",
}

# ── Experiment settings (reproducibility) ────────────────────────────────────
SEED = 42          # used for the split, CV shuffling and the stochastic models
TEST_SIZE = 0.30   # 70% train / 30% test, as requested in the assignment
CV_FOLDS = 5       # stratified k-fold for cross-validation and Grid Search
SCORING = "f1_macro"  # balanced classes -> macro F1 is a fair tuning objective

# Shared visual palette (kept consistent with the other chapters).
PALETTE = {1: "#005088", 2: "#11CAA0", 3: "#E8833A"}  # Kama / Rosa / Canadian


# ── Candidate classifiers + hyperparameter grids ─────────────────────────────
def _pipe(estimator) -> Pipeline:
    """
    Wrap an estimator behind a StandardScaler in a single Pipeline.

    Scaling inside the Pipeline guarantees the scaler is fit only on the
    training folds during cross-validation / Grid Search -> no data leakage.
    StandardScaler is required by the distance/margin-based models (KNN, SVM,
    Logistic Regression) and is harmless for the scale-invariant ones
    (Random Forest, Gaussian Naive Bayes), so we apply it uniformly.
    """
    return Pipeline([("scaler", StandardScaler()), ("clf", estimator)])


def build_models() -> dict[str, dict]:
    """
    Return the candidate models as ``{name: {"pipeline", "grid"}}``.

    Each ``pipeline`` is a fresh, untrained Scikit-Learn Pipeline; each ``grid``
    is the hyperparameter search space for ``GridSearchCV`` (keys are prefixed
    with ``clf__`` because the estimator is the ``"clf"`` step of the pipeline).
    """
    return {
        "KNN": {
            "pipeline": _pipe(KNeighborsClassifier()),
            "grid": {
                "clf__n_neighbors": [3, 5, 7, 9, 11, 15],
                "clf__weights": ["uniform", "distance"],
                "clf__p": [1, 2],  # 1 = Manhattan, 2 = Euclidean
            },
        },
        "SVM": {
            "pipeline": _pipe(SVC(random_state=SEED)),
            "grid": {
                "clf__C": [0.1, 1, 10, 100],
                "clf__gamma": ["scale", "auto", 0.01, 0.1, 1],
                "clf__kernel": ["rbf", "linear"],
            },
        },
        "Random Forest": {
            "pipeline": _pipe(RandomForestClassifier(random_state=SEED, n_jobs=-1)),
            "grid": {
                "clf__n_estimators": [100, 200, 300],
                "clf__max_depth": [None, 4, 6, 8],
                "clf__min_samples_leaf": [1, 2, 4],
                "clf__max_features": ["sqrt", "log2"],
            },
        },
        "Naive Bayes": {
            "pipeline": _pipe(GaussianNB()),
            "grid": {
                "clf__var_smoothing": [1e-9, 1e-8, 1e-7, 1e-6, 1e-5],
            },
        },
        "Logistic Regression": {
            # Defaults already use the lbfgs solver with L2 regularization, so we
            # only tune the inverse-regularization strength C. (Passing `penalty`
            # explicitly is deprecated in scikit-learn >= 1.8.)
            "pipeline": _pipe(LogisticRegression(max_iter=5000, random_state=SEED)),
            "grid": {
                "clf__C": [0.01, 0.1, 1, 10, 100],
            },
        },
    }
