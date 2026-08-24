"""Adapter from durable application values to the verified frozen bundle."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from tractor_usage.application.contracts import (
    CompleteWindow,
    LongitudinalSummary,
    ModelUnavailableError,
    ScoredDecision,
    StoredWindow,
)
from tractor_usage.application.episodes import episode_start_keys
from tractor_usage.modeling.artifact import FrozenUsageBundle, load_frozen_bundle


class FrozenBundleUsageModel:
    """Own the process-lifetime bundle; DataFrames are invocation-local."""

    def __init__(self, bundle: FrozenUsageBundle) -> None:
        self._bundle = bundle

    @classmethod
    def load(cls, model_dir: Path) -> "FrozenBundleUsageModel":
        try:
            return cls(
                load_frozen_bundle(
                    model_dir / "bundle.joblib", model_dir / "manifest.json"
                )
            )
        except (OSError, ValueError, TypeError) as error:
            raise ModelUnavailableError("approved frozen model is unavailable") from error

    @property
    def model_version(self) -> str:
        return self._bundle.model_version

    def score(self, tractor_id: str, window: CompleteWindow) -> ScoredDecision:
        if tuple(window.features) != tuple(self._bundle.feature_columns):
            if set(window.features) != set(self._bundle.feature_columns):
                raise ModelUnavailableError("window feature contract does not match approved model")
        row: dict[str, object] = {
            "tractor_id": tractor_id,
            "observed_at_utc": _utc(window.observed_at_utc).isoformat(),
            "mission_index": window.mission_index,
            "window_index": window.window_index,
            "sample_count": window.sample_count,
            "span_seconds": window.span_seconds,
            "window_quality": window.window_quality,
            **{
                name: np.nan if window.features[name] is None else window.features[name]
                for name in self._bundle.feature_columns
            },
            **window.physical_durations.as_model_columns(),
        }
        try:
            scored = self._bundle.score_windows(pd.DataFrame([row]))
        except (ValueError, TypeError, KeyError) as error:
            raise ModelUnavailableError("approved frozen model rejected the window") from error
        result = scored.iloc[0]
        return ScoredDecision(
            model_version=str(result["model_version"]),
            operational_regime=int(result["operational_regime"]),
            contextual_rarity_score=float(result["contextual_rarity_score"]),
            contextual_rarity_threshold=float(result["contextual_rarity_threshold"]),
            physical_eligible=bool(result["physical_eligible"]),
            physical_reasons=tuple(str(item) for item in result["physical_reasons"]),
            hybrid_alert=bool(result["hybrid_alert"]),
            contextual_reasons=tuple(
                {
                    "feature": str(item["feature"]),
                    "robust_deviation": float(item["robust_deviation"]),
                }
                for item in result["contextual_reasons"]
            ),
        )

    def aggregate(
        self, windows: tuple[StoredWindow, ...], *, as_of_utc: datetime
    ) -> tuple[LongitudinalSummary, ...]:
        starts = episode_start_keys(windows)
        rows = []
        for window in sorted(windows, key=lambda item: item.observed_at_utc):
            rows.append(
                {
                    "tractor_id": window.tractor_id,
                    "observed_at_utc": _utc(window.observed_at_utc).isoformat(),
                    "mission_index": window.mission_index,
                    "window_index": window.window_index,
                    "sample_count": window.sample_count,
                    **window.physical_durations.as_model_columns(),
                    "hybrid_alert": window.decision.hybrid_alert,
                    "hybrid_episode_start": window.idempotency_key in starts,
                    "operational_regime": window.decision.operational_regime,
                }
            )
        frame = pd.DataFrame(rows)
        try:
            scores = self._bundle.aggregate(frame, _utc(as_of_utc).isoformat())
        except (ValueError, TypeError, KeyError) as error:
            raise ModelUnavailableError("approved frozen model could not aggregate history") from error
        return tuple(
            LongitudinalSummary(
                horizon_days=score.horizon_days,
                status=score.status,
                as_of_utc=_timestamp(score.as_of_utc),
                observed_hours=score.observed_hours,
                active_days=score.active_days,
                calendar_coverage=score.calendar_coverage,
                confidence=score.confidence,
                physical_exposure_seconds_per_hour=score.physical_exposure_seconds_per_hour,
                alert_exposure_seconds_per_hour=score.alert_exposure_seconds_per_hour,
                episodes_per_hour=score.episodes_per_hour,
                episode_count=score.episode_count,
                represented_conditions=score.represented_conditions,
                predominant_regimes=score.predominant_regimes,
                component_percentiles=score.component_percentiles,
                relative_exposure_score=score.relative_exposure_score,
            )
            for score in scores
        )


def _utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc)


def _timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(timezone.utc)
