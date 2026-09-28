"""Frozen model-selection orchestration that never opens test by default."""

from __future__ import annotations

import pandas as pd

from tractor_usage.features.schema import model_feature_columns
from tractor_usage.modeling.hybrid import (
    HybridUsageModel,
    evaluate_hybrid_candidates,
)
from tractor_usage.modeling.longitudinal import (
    aggregate_integrity_horizons,
    fit_longitudinal_baseline,
)
from tractor_usage.modeling.regimes import evaluate_regime_candidates


def selection_splits(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return only model-selection rows; test is deliberately excluded."""

    if "split" not in frame:
        raise ValueError("windows dataset must contain split")
    train = frame.loc[frame["split"].eq("train")].copy()
    validation = frame.loc[frame["split"].eq("validation")].copy()
    if train.empty or validation.empty:
        raise ValueError("both train and validation rows are required")
    return train, validation


def run_selection(
    frame: pd.DataFrame,
) -> tuple[dict[str, object], HybridUsageModel | None]:
    """Select models using train and validation, returning a JSON-safe report."""

    train, validation = selection_splits(frame)
    features = model_feature_columns(frame.columns)
    regime = evaluate_regime_candidates(train, validation, features)
    report: dict[str, object] = {
        "feature_schema": "usage_context_v2",
        "requested_features": len(features),
        "split_rows": {
            name: int(frame["split"].eq(name).sum())
            for name in ("train", "validation", "test")
        },
        "regime": regime.report(),
        "hybrid": None,
        "validation_longitudinal": None,
        "test": {"status": "CLOSED", "scored": False},
    }
    if not regime.accepted or regime.model is None:
        return report, None

    hybrid = evaluate_hybrid_candidates(train, validation, regime.model)
    report["hybrid"] = hybrid.report()
    if not hybrid.accepted or hybrid.model is None:
        return report, None

    scored_train = hybrid.model.score(train)
    scored_history = hybrid.model.score(
        pd.concat([train, validation], ignore_index=True).sort_values(
            "observed_at_utc", kind="stable"
        )
    )
    baseline = fit_longitudinal_baseline(scored_train)
    as_of = pd.to_datetime(validation["observed_at_utc"], utc=True).max()
    report["validation_longitudinal"] = [
        score.to_dict()
        for score in aggregate_integrity_horizons(
            scored_history,
            as_of,
            baseline,
        )
    ]
    return report, hybrid.model
