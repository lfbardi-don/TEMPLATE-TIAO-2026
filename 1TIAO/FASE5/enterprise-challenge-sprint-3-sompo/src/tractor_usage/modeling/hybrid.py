"""Explainable hybrid detection: physical exposure and contextual rarity."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from tractor_usage.modeling.regimes import RegimeModel


RarityKind = Literal["isolation_forest", "robust_rms"]

PHYSICAL_CONDITIONS = (
    ("lugging", "lugging__sum"),
    ("overload_torque", "overload_torque__sum"),
    ("loaded_high_slip", "loaded_high_slip__sum"),
    ("thermal_under_load", "thermal_under_load__sum"),
    ("harsh_torque_rise", "harsh_torque_rise__sum"),
)

REQUIRED_IDENTITY_COLUMNS = (
    "observed_at_utc",
    "mission_index",
    "window_index",
    "sample_count",
)


@dataclass(frozen=True)
class PhysicalEligibility:
    eligible: np.ndarray
    reasons: tuple[tuple[str, ...], ...]
    condition_flags: pd.DataFrame


@dataclass(frozen=True)
class HybridCandidateMetrics:
    kind: RarityKind
    threshold_quantile: float
    alert_fraction: float
    physical_eligible_fraction: float
    contextual_retention: float
    represented_families: int
    alert_windows_by_family: dict[str, int]
    episodes: int
    episodes_per_observed_hour: float
    active_alert_dates: int
    maximum_daily_episode_share: float
    explanations_complete: bool
    passes_gate: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class HybridUsageModel:
    kind: RarityKind
    threshold_quantile: float
    regime_model: RegimeModel
    detectors: dict[int, IsolationForest]
    thresholds: dict[int, float]
    reference_median: dict[int, np.ndarray]
    reference_iqr: dict[int, np.ndarray]
    minimum_physical_seconds: float = 5.0

    def score(self, frame: pd.DataFrame) -> pd.DataFrame:
        """Return an auditable decision for every operational window."""

        _validate_identity(frame)
        eligibility = physical_eligibility(
            frame, minimum_seconds=self.minimum_physical_seconds
        )
        regimes = self.regime_model.predict(frame)
        transformed = self.regime_model.transform(frame)
        scores = np.full(len(frame), np.nan, dtype=float)
        thresholds = np.full(len(frame), np.nan, dtype=float)

        for regime in np.unique(regimes):
            regime_id = int(regime)
            if regime_id not in self.thresholds or regime_id not in self.reference_median:
                raise ValueError(f"regime {regime_id} has no training reference")
            mask = regimes == regime_id
            scores[mask] = _rarity_score(
                self.kind,
                transformed[mask],
                detector=self.detectors.get(regime_id),
                median=self.reference_median[regime_id],
                iqr=self.reference_iqr[regime_id],
            )
            thresholds[mask] = self.thresholds[regime_id]

        alerts = eligibility.eligible & (scores >= thresholds)
        result = frame.copy()
        result["operational_regime"] = regimes
        result["contextual_rarity_score"] = scores
        result["contextual_rarity_threshold"] = thresholds
        result["physical_eligible"] = eligibility.eligible
        result["physical_reasons"] = eligibility.reasons
        result["hybrid_alert"] = alerts
        result["contextual_reasons"] = self._contextual_reasons(
            transformed, regimes, alerts
        )
        result["hybrid_episode_start"] = episode_start_flags(result, alerts)
        return result

    def _contextual_reasons(
        self,
        transformed: np.ndarray,
        regimes: np.ndarray,
        alerts: np.ndarray,
    ) -> tuple[tuple[dict[str, float | str], ...], ...]:
        explanations: list[tuple[dict[str, float | str], ...]] = []
        for position, regime in enumerate(regimes):
            if not alerts[position]:
                explanations.append(())
                continue
            regime_id = int(regime)
            deviation = np.abs(
                (transformed[position] - self.reference_median[regime_id])
                / self.reference_iqr[regime_id]
            )
            top = np.argsort(deviation)[::-1][:3]
            explanations.append(
                tuple(
                    {
                        "feature": self.regime_model.feature_columns[index],
                        "robust_deviation": float(deviation[index]),
                    }
                    for index in top
                )
            )
        return tuple(explanations)


@dataclass
class HybridSelection:
    candidates: tuple[HybridCandidateMetrics, ...]
    selected_metrics: HybridCandidateMetrics | None
    model: HybridUsageModel | None

    @property
    def accepted(self) -> bool:
        return self.selected_metrics is not None and self.selected_metrics.passes_gate

    def report(self) -> dict[str, object]:
        return {
            "accepted": self.accepted,
            "selected": (
                self.selected_metrics.to_dict()
                if self.selected_metrics is not None
                else None
            ),
            "candidates": [candidate.to_dict() for candidate in self.candidates],
        }


def _validate_identity(frame: pd.DataFrame) -> None:
    missing = sorted(column for column in REQUIRED_IDENTITY_COLUMNS if column not in frame)
    if missing:
        raise ValueError(f"missing operational identity columns: {', '.join(missing)}")
    parsed: list[pd.Timestamp] = []
    for raw in frame["observed_at_utc"]:
        try:
            timestamp = pd.Timestamp(raw)
        except (TypeError, ValueError) as error:
            raise ValueError("observed_at_utc contains invalid timestamps") from error
        if pd.isna(timestamp) or timestamp.tzinfo is None:
            raise ValueError("observed_at_utc must contain timezone-aware timestamps")
        parsed.append(timestamp.tz_convert("UTC"))
    timestamps = pd.Series(parsed, dtype="datetime64[ns, UTC]")
    if not timestamps.is_monotonic_increasing:
        raise ValueError("observed_at_utc must be monotonic")
    sample_count = pd.to_numeric(frame["sample_count"], errors="coerce")
    if sample_count.isna().any() or sample_count.le(0).any():
        raise ValueError("sample_count must contain positive numeric values")
    if frame[["mission_index", "window_index"]].isna().any().any():
        raise ValueError("mission_index and window_index must not be null")


def physical_eligibility(
    frame: pd.DataFrame, *, minimum_seconds: float = 5.0
) -> PhysicalEligibility:
    """Evaluate versioned physical rules without learning or hidden weights."""

    if minimum_seconds <= 0:
        raise ValueError("minimum_seconds must be positive")
    missing = sorted(column for _, column in PHYSICAL_CONDITIONS if column not in frame)
    if missing:
        raise ValueError(f"missing physical condition columns: {', '.join(missing)}")

    condition_values: dict[str, np.ndarray] = {}
    for name, column in PHYSICAL_CONDITIONS:
        values = pd.to_numeric(frame[column], errors="coerce")
        if values.isna().any() or values.lt(0.0).any() or values.gt(60.0).any():
            raise ValueError(
                f"{column} must contain observed durations between 0 and 60 seconds"
            )
        condition_values[name] = values.ge(minimum_seconds).to_numpy(dtype=bool)
    condition_flags = pd.DataFrame(condition_values, index=frame.index)
    eligible = condition_flags.any(axis=1).to_numpy(dtype=bool)
    reasons = tuple(
        tuple(name for name in condition_flags if bool(row[name]))
        for _, row in condition_flags.iterrows()
    )
    return PhysicalEligibility(eligible, reasons, condition_flags)


def episode_start_flags(frame: pd.DataFrame, alerts: np.ndarray) -> np.ndarray:
    """Mark alert starts while respecting mission and window adjacency."""

    if len(frame) != len(alerts):
        raise ValueError("frame and alert flags must have the same length")
    if not {"mission_index", "window_index"}.issubset(frame.columns):
        raise ValueError("mission_index and window_index are required for episodes")
    alert_series = pd.Series(np.asarray(alerts, dtype=bool), index=frame.index)
    previous_alert = alert_series.shift(fill_value=False)
    same_mission = frame["mission_index"].eq(frame["mission_index"].shift())
    same_tractor = (
        frame["tractor_id"].eq(frame["tractor_id"].shift())
        if "tractor_id" in frame
        else pd.Series(True, index=frame.index)
    )
    adjacent = frame["window_index"].eq(frame["window_index"].shift() + 1)
    return (alert_series & ~(previous_alert & same_tractor & same_mission & adjacent)).to_numpy(
        dtype=bool
    )


def _fit_isolation_forest(values: np.ndarray) -> IsolationForest:
    detector = IsolationForest(
        n_estimators=300,
        max_samples="auto",
        contamination="auto",
        random_state=0,
        n_jobs=-1,
    )
    detector.fit(values)
    return detector


def _rarity_score(
    kind: RarityKind,
    values: np.ndarray,
    *,
    detector: IsolationForest | None,
    median: np.ndarray,
    iqr: np.ndarray,
) -> np.ndarray:
    if kind == "isolation_forest":
        if detector is None:
            raise ValueError("isolation_forest scoring requires a fitted detector")
        return -np.asarray(detector.score_samples(values), dtype=float)
    robust_z = (values - median) / iqr
    return np.sqrt(np.mean(np.square(robust_z), axis=1))


def _candidate_metrics(
    validation: pd.DataFrame,
    alerts: np.ndarray,
    eligibility: PhysicalEligibility,
    *,
    kind: RarityKind,
    threshold_quantile: float,
    explanations_complete: bool = True,
) -> HybridCandidateMetrics:
    alert_fraction = float(alerts.mean()) if len(alerts) else 0.0
    eligible_fraction = (
        float(eligibility.eligible.mean()) if len(eligibility.eligible) else 0.0
    )
    eligible_count = int(eligibility.eligible.sum())
    retention = float(alerts.sum() / eligible_count) if eligible_count else 0.0
    family_counts = {
        name: int((alerts & eligibility.condition_flags[name].to_numpy()).sum())
        for name, _ in PHYSICAL_CONDITIONS
    }
    represented = sum(count >= 5 for count in family_counts.values())
    starts = episode_start_flags(validation, alerts)
    episodes = int(starts.sum())
    observed_hours = float(validation["sample_count"].sum() / 3600.0)
    episodes_per_hour = episodes / observed_hours if observed_hours else np.inf
    dates = pd.to_datetime(validation["observed_at_utc"], utc=True).dt.date
    episode_dates = dates[starts]
    daily_episodes = episode_dates.value_counts()
    active_dates = int(len(daily_episodes))
    maximum_daily_share = (
        float(daily_episodes.max() / episodes) if episodes else 1.0
    )
    passes = bool(
        0.01 <= alert_fraction <= 0.10
        and 0.05 <= retention <= 0.50
        and represented >= 3
        and episodes >= 5
        and episodes_per_hour <= 2.0
        and active_dates >= 3
        and maximum_daily_share <= 0.50
        and explanations_complete
    )
    return HybridCandidateMetrics(
        kind=kind,
        threshold_quantile=threshold_quantile,
        alert_fraction=alert_fraction,
        physical_eligible_fraction=eligible_fraction,
        contextual_retention=retention,
        represented_families=represented,
        alert_windows_by_family=family_counts,
        episodes=episodes,
        episodes_per_observed_hour=float(episodes_per_hour),
        active_alert_dates=active_dates,
        maximum_daily_episode_share=maximum_daily_share,
        explanations_complete=explanations_complete,
        passes_gate=passes,
    )


def audit_scored_hybrid(
    frame: pd.DataFrame,
    scored: pd.DataFrame,
    model: HybridUsageModel,
) -> HybridCandidateMetrics:
    """Apply the frozen gates to already-scored, held-out windows."""

    if len(frame) != len(scored):
        raise ValueError("frame and scored output must have the same length")
    required = {
        "operational_regime",
        "contextual_rarity_score",
        "contextual_rarity_threshold",
        "physical_eligible",
        "physical_reasons",
        "hybrid_alert",
        "contextual_reasons",
    }
    missing = sorted(required - set(scored.columns))
    if missing:
        raise ValueError(f"missing scored hybrid columns: {', '.join(missing)}")

    eligibility = physical_eligibility(
        frame, minimum_seconds=model.minimum_physical_seconds
    )
    alerts = scored["hybrid_alert"].to_numpy(dtype=bool)
    reported_eligibility = scored["physical_eligible"].to_numpy(dtype=bool)
    if not np.array_equal(eligibility.eligible, reported_eligibility):
        raise ValueError("scored physical eligibility does not match frozen rules")
    scores = scored["contextual_rarity_score"].to_numpy(dtype=float)
    thresholds = scored["contextual_rarity_threshold"].to_numpy(dtype=float)
    expected_alerts = eligibility.eligible & (scores >= thresholds)
    if not np.array_equal(alerts, expected_alerts):
        raise ValueError("scored alerts do not match the frozen hybrid decision")

    explanations_complete = all(
        not alert
        or (
            pd.notna(scored.iloc[position]["operational_regime"])
            and np.isfinite(scores[position])
            and np.isfinite(thresholds[position])
            and len(scored.iloc[position]["physical_reasons"]) >= 1
            and len(scored.iloc[position]["contextual_reasons"]) == 3
        )
        for position, alert in enumerate(alerts)
    )
    return _candidate_metrics(
        frame,
        alerts,
        eligibility,
        kind=model.kind,
        threshold_quantile=model.threshold_quantile,
        explanations_complete=explanations_complete,
    )


def evaluate_hybrid_candidates(
    train: pd.DataFrame,
    validation: pd.DataFrame,
    regime_model: RegimeModel,
    *,
    threshold_quantiles: tuple[float, ...] = (
        0.90,
        0.92,
        0.94,
        0.95,
        0.96,
        0.97,
        0.98,
        0.99,
    ),
    minimum_physical_seconds: float = 5.0,
) -> HybridSelection:
    """Fit rarity on train and choose a hybrid operating point on validation."""

    _validate_identity(train)
    _validate_identity(validation)
    validation_eligibility = physical_eligibility(
        validation, minimum_seconds=minimum_physical_seconds
    )
    train_regimes = regime_model.predict(train)
    validation_regimes = regime_model.predict(validation)
    x_train = regime_model.transform(train)
    x_validation = regime_model.transform(validation)

    references: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    detectors: dict[int, IsolationForest] = {}
    train_scores: dict[RarityKind, dict[int, np.ndarray]] = {
        "isolation_forest": {},
        "robust_rms": {},
    }
    validation_scores: dict[RarityKind, np.ndarray] = {
        "isolation_forest": np.full(len(validation), np.nan, dtype=float),
        "robust_rms": np.full(len(validation), np.nan, dtype=float),
    }

    for regime in sorted(np.unique(train_regimes)):
        regime_id = int(regime)
        train_mask = train_regimes == regime_id
        validation_mask = validation_regimes == regime_id
        values = x_train[train_mask]
        median = np.median(values, axis=0)
        q75, q25 = np.percentile(values, [75, 25], axis=0)
        iqr = np.maximum(q75 - q25, 1e-6)
        references[regime_id] = (median, iqr)
        detector = _fit_isolation_forest(values)
        detectors[regime_id] = detector

        for kind in ("isolation_forest", "robust_rms"):
            train_scores[kind][regime_id] = _rarity_score(
                kind,
                values,
                detector=detector if kind == "isolation_forest" else None,
                median=median,
                iqr=iqr,
            )
            if validation_mask.any():
                validation_scores[kind][validation_mask] = _rarity_score(
                    kind,
                    x_validation[validation_mask],
                    detector=detector if kind == "isolation_forest" else None,
                    median=median,
                    iqr=iqr,
                )

    unknown_regimes = sorted(set(np.unique(validation_regimes)) - set(references))
    if unknown_regimes:
        raise ValueError(f"validation contains unknown regimes: {unknown_regimes}")

    candidates: list[HybridCandidateMetrics] = []
    thresholds_by_candidate: dict[tuple[RarityKind, float], dict[int, float]] = {}
    for kind in ("isolation_forest", "robust_rms"):
        for quantile in threshold_quantiles:
            thresholds = {
                regime: float(np.quantile(scores, quantile))
                for regime, scores in train_scores[kind].items()
            }
            rare = np.asarray(
                [
                    score >= thresholds[int(regime)]
                    for score, regime in zip(
                        validation_scores[kind], validation_regimes, strict=True
                    )
                ],
                dtype=bool,
            )
            alerts = validation_eligibility.eligible & rare
            candidates.append(
                _candidate_metrics(
                    validation,
                    alerts,
                    validation_eligibility,
                    kind=kind,
                    threshold_quantile=quantile,
                )
            )
            thresholds_by_candidate[(kind, quantile)] = thresholds

    accepted = [candidate for candidate in candidates if candidate.passes_gate]
    kind_tie_break = {"isolation_forest": 1, "robust_rms": 0}
    selected = max(
        accepted,
        key=lambda value: (
            value.represented_families,
            value.active_alert_dates,
            -abs(value.episodes_per_observed_hour - 1.0),
            -value.alert_fraction,
            kind_tie_break[value.kind],
        ),
        default=None,
    )
    if selected is None:
        return HybridSelection(tuple(candidates), None, None)

    return HybridSelection(
        candidates=tuple(candidates),
        selected_metrics=selected,
        model=HybridUsageModel(
            kind=selected.kind,
            threshold_quantile=selected.threshold_quantile,
            regime_model=regime_model,
            detectors=detectors if selected.kind == "isolation_forest" else {},
            thresholds=thresholds_by_candidate[
                (selected.kind, selected.threshold_quantile)
            ],
            reference_median={regime: values[0] for regime, values in references.items()},
            reference_iqr={regime: values[1] for regime, values in references.items()},
            minimum_physical_seconds=minimum_physical_seconds,
        ),
    )
