"""
Data access layer — UCI "Seeds" dataset (FASE 4 / CAP 3).

The original file (``data/seeds_dataset.txt``) is the raw UCI distribution:
210 rows, 8 whitespace-separated columns, **no header**. A handful of rows use
more than one tab between values (e.g. ``2.7\t\t5``), so a fixed-width or
single-character separator would misparse them — we read with the regex
separator ``\\s+`` (one-or-more whitespace), which is robust to that quirk.

This module is the single place that knows how to turn the raw file into a tidy,
labeled DataFrame, so the notebook (and any script) stays free of parsing logic.

Usage:
    python src/data.py            # build data/seeds_clean.csv from the raw file
"""
from __future__ import annotations

import pandas as pd

from config import (
    RAW_DATASET_PATH, CLEAN_DATASET_PATH, COLUMN_NAMES,
    CLASS_MAP, TARGET, TARGET_NAME,
)


def load_raw() -> pd.DataFrame:
    """
    Read the raw UCI file into a DataFrame with the 8 named columns.

    Uses the ``\\s+`` regex separator (Python engine) to tolerate the rows that
    contain repeated tabs between values.
    """
    if not RAW_DATASET_PATH.exists():
        raise FileNotFoundError(
            f"Raw dataset not found at {RAW_DATASET_PATH}. "
            "Download it from https://archive.ics.uci.edu/dataset/236/seeds"
        )
    df = pd.read_csv(
        RAW_DATASET_PATH,
        sep=r"\s+",
        header=None,
        names=COLUMN_NAMES,
        engine="python",
    )
    return df


def load_seeds() -> pd.DataFrame:
    """
    Return the tidy dataset: the 7 features, the integer ``variety`` label and a
    human-readable ``variety_name`` column (Kama / Rosa / Canadian).

    Performs light validation so any surprise in the source file fails loudly
    instead of silently corrupting the analysis downstream.
    """
    df = load_raw()

    # ── Validation ───────────────────────────────────────────────────────────
    if df.shape[1] != len(COLUMN_NAMES):
        raise ValueError(
            f"Expected {len(COLUMN_NAMES)} columns, parsed {df.shape[1]}. "
            "The raw file may have an unexpected format."
        )
    unknown = set(df[TARGET].unique()) - set(CLASS_MAP)
    if unknown:
        raise ValueError(f"Unexpected class labels in the data: {unknown}")

    # Integer class -> readable variety name (categorical, ordered as in CLASS_MAP).
    df[TARGET] = df[TARGET].astype(int)
    df[TARGET_NAME] = df[TARGET].map(CLASS_MAP).astype(
        pd.CategoricalDtype(categories=list(CLASS_MAP.values()), ordered=False)
    )
    return df


def build_clean_csv() -> pd.DataFrame:
    """Build ``data/seeds_clean.csv`` from the raw file and return the DataFrame."""
    df = load_seeds()
    df.to_csv(CLEAN_DATASET_PATH, index=False)
    return df


def main() -> None:
    df = build_clean_csv()
    print(f"[OK] Clean dataset written to {CLEAN_DATASET_PATH}")
    print(f"     shape = {df.shape[0]} rows x {df.shape[1]} columns")
    print(f"     missing values = {int(df.isna().sum().sum())}")
    print("     class balance:")
    counts = df[TARGET_NAME].value_counts().reindex(CLASS_MAP.values())
    for name, n in counts.items():
        print(f"       {name:<10} {n}")


if __name__ == "__main__":
    main()
