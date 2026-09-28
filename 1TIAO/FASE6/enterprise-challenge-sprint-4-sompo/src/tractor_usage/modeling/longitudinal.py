"""Explainable 7/15/30-day summaries for accepted hybrid alerts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

import numpy as np
import pandas as pd

from tractor_usage.modeling.hybrid import PHYSICAL_CONDITIONS


DEFAULT_HORIZONS = (7, 15, 30)
COMPONENT_NAMES = (
    "physical_exposure_seconds_per_hour",
    "alert_exposure_seconds_per_hour",
    "episodes_per_hour",
)


@dataclass(frozen=True)
class LongitudinalBaseline:
    component_distributions: dict[int, dict[str, tuple[float, ...]]]


@dataclass(frozen=True)
class LongitudinalScore:
    horizon_days: int
    status: Literal["OK", "NO_DATA"]
    as_of_utc: str
    observed_hours: float
    active_days: int
    calendar_coverage: float
    confidence: Literal["LOW", "MEDIUM", "HIGH"]
    physical_exposure_seconds_per_hour: float | None
    alert_exposure_seconds_per_hour: float | None
    episodes_per_hour: float | None
    episode_count: int
    represented_conditions: tuple[str, ...]
    predominant_regimes: tuple[int, ...]
    component_percentiles: dict[str, float]
    relative_exposure_score: float | None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _timestamps(frame: pd.DataFrame) -> pd.Series:
    if "observed_at_utc" not in frame:
        raise ValueError("observed_at_utc is required")
    parsed: list[pd.Timestamp] = []
    for raw in frame["observed_at_utc"]:
        try:
            timestamp = pd.Timestamp(raw)
        except (TypeError, ValueError) as error:
            raise ValueError("observed_at_utc contains invalid timestamps") from error
        if pd.isna(timestamp) or timestamp.tzinfo is None:
            raise ValueError("observed_at_utc must contain timezone-aware timestamps")
        parsed.append(timestamp.tz_convert("UTC"))
    result = pd.Series(parsed, index=frame.index, dtype="datetime64[ns, UTC]")
    if not result.is_monotonic_increasing:
        raise ValueError("observed_at_utc must be monotonic")
    return result


def _validate_scored_frame(frame: pd.DataFrame) -> pd.Series:
    required = {
        "sample_count",
        "severe_exposure__sum",
        "hybrid_alert",
        "hybrid_episode_start",
        "operational_regime",
        *(column for _, column in PHYSICAL_CONDITIONS),
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"missing longitudinal columns: {', '.join(missing)}")
    if "tractor_id" in frame:
        tractor_ids = frame["tractor_id"].astype("string")
        if tractor_ids.isna().any() or tractor_ids.str.strip().eq("").any():
            raise ValueError("tractor_id must contain stable non-empty identifiers")
        if tractor_ids.str.strip().nunique() > 1:
            raise ValueError("longitudinal aggregation cannot mix tractor identifiers")
    return _timestamps(frame)


def _effective_observed_seconds(frame: pd.DataFrame) -> pd.Series:
    sample_count = pd.to_numeric(frame["sample_count"], errors="coerce")
    values = sample_count.to_numpy(dtype=float)
    if not np.isfinite(values).all() or sample_count.lt(0.0).any():
        raise ValueError("sample_count must contain finite non-negative values")
    return sample_count.clip(upper=60.0)


def _rates(frame: pd.DataFrame) -> dict[str, float]:
    observed_hours = float(_effective_observed_seconds(frame).sum() / 3600.0)
    if observed_hours <= 0:
        return {name: 0.0 for name in COMPONENT_NAMES}
    alerts = frame["hybrid_alert"].to_numpy(dtype=bool)
    physical_seconds = float(frame["severe_exposure__sum"].sum())
    alert_seconds = float(frame.loc[alerts, "severe_exposure__sum"].sum())
    episodes = int(frame["hybrid_episode_start"].sum())
    return {
        "physical_exposure_seconds_per_hour": physical_seconds / observed_hours,
        "alert_exposure_seconds_per_hour": alert_seconds / observed_hours,
        "episodes_per_hour": episodes / observed_hours,
    }


def _window(
    frame: pd.DataFrame,
    window_closes: pd.Series,
    *,
    as_of_utc: pd.Timestamp,
    horizon_days: int,
) -> pd.DataFrame:
    start = as_of_utc - pd.Timedelta(days=horizon_days)
    return frame.loc[(window_closes > start) & (window_closes <= as_of_utc)]


def fit_longitudinal_baseline(
    scored_train: pd.DataFrame,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
) -> LongitudinalBaseline:
    """Fit empirical component distributions using complete train history only."""

    if not horizons or any(horizon <= 0 for horizon in horizons):
        raise ValueError("horizons must contain positive day counts")
    timestamps = _validate_scored_frame(scored_train)
    window_closes = timestamps + pd.Timedelta(seconds=60)
    if scored_train.empty:
        raise ValueError("scored_train must not be empty")
    first_observation = window_closes.min()
    active_dates = sorted(window_closes.dt.floor("D").unique())
    distributions: dict[int, dict[str, tuple[float, ...]]] = {}

    for horizon in horizons:
        values = {name: [] for name in COMPONENT_NAMES}
        for active_date in active_dates:
            endpoint = pd.Timestamp(active_date) + pd.Timedelta(days=1) - pd.Timedelta(
                nanoseconds=1
            )
            if endpoint - pd.Timedelta(days=horizon) < first_observation:
                continue
            part = _window(
                scored_train,
                window_closes,
                as_of_utc=endpoint,
                horizon_days=horizon,
            )
            if float(_effective_observed_seconds(part).sum()) <= 0:
                continue
            rates = _rates(part)
            for name, value in rates.items():
                values[name].append(value)
        if not all(values[name] for name in COMPONENT_NAMES):
            raise ValueError(f"insufficient training history for {horizon}-day baseline")
        distributions[horizon] = {
            name: tuple(float(value) for value in values[name])
            for name in COMPONENT_NAMES
        }
    return LongitudinalBaseline(distributions)


def _percentile(value: float, reference: tuple[float, ...]) -> float:
    values = np.asarray(reference, dtype=float)
    return float(100.0 * np.mean(values <= value))


def _confidence(calendar_coverage: float) -> Literal["LOW", "MEDIUM", "HIGH"]:
    if calendar_coverage < 0.25:
        return "LOW"
    if calendar_coverage < 0.60:
        return "MEDIUM"
    return "HIGH"


def aggregate_integrity_horizons(
    scored: pd.DataFrame,
    as_of_utc: str | pd.Timestamp,
    baseline: LongitudinalBaseline,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
) -> tuple[LongitudinalScore, ...]:
    """Aggregate accepted events without converting absent telemetry to zero use."""

    timestamps = _validate_scored_frame(scored)
    window_closes = timestamps + pd.Timedelta(seconds=60)
    as_of = pd.Timestamp(as_of_utc)
    if pd.isna(as_of) or as_of.tzinfo is None:
        raise ValueError("as_of_utc must be a timezone-aware timestamp")
    as_of = as_of.tz_convert("UTC")
    results: list[LongitudinalScore] = []

    for horizon in horizons:
        if horizon not in baseline.component_distributions:
            raise ValueError(f"missing {horizon}-day longitudinal baseline")
        part = _window(
            scored,
            window_closes,
            as_of_utc=as_of,
            horizon_days=horizon,
        )
        observed_hours = float(_effective_observed_seconds(part).sum() / 3600.0)
        if observed_hours <= 0:
            results.append(
                LongitudinalScore(
                    horizon_days=horizon,
                    status="NO_DATA",
                    as_of_utc=as_of.isoformat(),
                    observed_hours=0.0,
                    active_days=0,
                    calendar_coverage=0.0,
                    confidence="LOW",
                    physical_exposure_seconds_per_hour=None,
                    alert_exposure_seconds_per_hour=None,
                    episodes_per_hour=None,
                    episode_count=0,
                    represented_conditions=(),
                    predominant_regimes=(),
                    component_percentiles={},
                    relative_exposure_score=None,
                )
            )
            continue

        rates = _rates(part)
        active_days = int(timestamps.loc[part.index].dt.date.nunique())
        coverage = min(1.0, active_days / horizon)
        alerts = part["hybrid_alert"].to_numpy(dtype=bool)
        represented = tuple(
            name
            for name, column in PHYSICAL_CONDITIONS
            if bool((alerts & part[column].ge(5.0).to_numpy(dtype=bool)).any())
        )
        regime_source = part.loc[alerts, "operational_regime"]
        if regime_source.empty:
            regime_source = part["operational_regime"]
        predominant = tuple(
            int(regime)
            for regime in regime_source.value_counts().index[:3].tolist()
        )
        percentiles = {
            name: _percentile(
                rates[name], baseline.component_distributions[horizon][name]
            )
            for name in COMPONENT_NAMES
        }
        results.append(
            LongitudinalScore(
                horizon_days=horizon,
                status="OK",
                as_of_utc=as_of.isoformat(),
                observed_hours=observed_hours,
                active_days=active_days,
                calendar_coverage=coverage,
                confidence=_confidence(coverage),
                physical_exposure_seconds_per_hour=rates[
                    "physical_exposure_seconds_per_hour"
                ],
                alert_exposure_seconds_per_hour=rates[
                    "alert_exposure_seconds_per_hour"
                ],
                episodes_per_hour=rates["episodes_per_hour"],
                episode_count=int(part["hybrid_episode_start"].sum()),
                represented_conditions=represented,
                predominant_regimes=predominant,
                component_percentiles=percentiles,
                relative_exposure_score=float(np.mean(list(percentiles.values()))),
            )
        )
    return tuple(results)
