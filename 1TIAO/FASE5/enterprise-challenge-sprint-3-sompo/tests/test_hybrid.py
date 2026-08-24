import numpy as np
import pandas as pd
import pytest

from tractor_usage.modeling.hybrid import (
    HybridUsageModel,
    audit_scored_hybrid,
    episode_start_flags,
    evaluate_hybrid_candidates,
    physical_eligibility,
)


class _SingleRegime:
    feature_columns = ("a", "b", "c")

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        return np.zeros(len(frame), dtype=int)

    def transform(self, frame: pd.DataFrame) -> np.ndarray:
        return frame.loc[:, self.feature_columns].to_numpy(dtype=float)


def _physical_columns(rows: int) -> dict[str, list[float]]:
    return {
        "lugging__sum": [0.0] * rows,
        "overload_torque__sum": [0.0] * rows,
        "loaded_high_slip__sum": [0.0] * rows,
        "thermal_under_load__sum": [0.0] * rows,
        "harsh_torque_rise__sum": [0.0] * rows,
        "severe_exposure__sum": [0.0] * rows,
    }


def test_physical_eligibility_returns_exact_reasons() -> None:
    frame = pd.DataFrame(_physical_columns(2))
    frame.loc[0, "lugging__sum"] = 5.0
    frame.loc[0, "loaded_high_slip__sum"] = 7.0

    result = physical_eligibility(frame)

    assert result.eligible.tolist() == [True, False]
    assert result.reasons == (("lugging", "loaded_high_slip"), ())


def test_physical_eligibility_rejects_unknown_duration() -> None:
    frame = pd.DataFrame(_physical_columns(1))
    frame.loc[0, "lugging__sum"] = np.nan

    with pytest.raises(ValueError, match="observed durations"):
        physical_eligibility(frame)


def test_hybrid_decision_requires_rule_and_rarity_and_explains_alert() -> None:
    frame = pd.DataFrame(
        {
            "observed_at_utc": pd.date_range(
                "2024-01-01", periods=3, freq="min", tz="UTC"
            ),
            "mission_index": [1, 1, 1],
            "window_index": [0, 1, 2],
            "sample_count": [60, 60, 60],
            "a": [0.0, 4.0, 4.0],
            "b": [0.0, 3.0, 3.0],
            "c": [0.0, 2.0, 2.0],
            **_physical_columns(3),
        }
    )
    frame.loc[1, ["lugging__sum", "severe_exposure__sum"]] = 8.0
    model = HybridUsageModel(
        kind="robust_rms",
        threshold_quantile=0.95,
        regime_model=_SingleRegime(),
        detectors={},
        thresholds={0: 1.0},
        reference_median={0: np.zeros(3)},
        reference_iqr={0: np.ones(3)},
    )

    scored = model.score(frame)

    assert scored["hybrid_alert"].tolist() == [False, True, False]
    assert scored.loc[1, "physical_reasons"] == ("lugging",)
    assert len(scored.loc[1, "contextual_reasons"]) == 3
    assert scored.loc[1, "operational_regime"] == 0
    assert scored.loc[1, "contextual_rarity_score"] >= scored.loc[
        1, "contextual_rarity_threshold"
    ]
    audit = audit_scored_hybrid(frame, scored, model)
    assert audit.explanations_complete


def test_episode_starts_respect_gaps_and_missions() -> None:
    frame = pd.DataFrame(
        {
            "mission_index": [1, 1, 1, 2],
            "window_index": [0, 1, 3, 0],
        }
    )
    alerts = np.array([True, True, True, True])

    assert episode_start_flags(frame, alerts).tolist() == [True, False, True, True]


def test_episode_starts_do_not_continue_across_tractors() -> None:
    frame = pd.DataFrame(
        {
            "tractor_id": ["tractor-a", "tractor-b", "tractor-b"],
            "mission_index": [1, 1, 1],
            "window_index": [0, 1, 2],
        }
    )
    alerts = np.array([True, True, True])

    assert episode_start_flags(frame, alerts).tolist() == [True, True, False]


def _candidate_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(12)
    train_rows = 500
    train = pd.DataFrame(
        {
            "observed_at_utc": pd.date_range(
                "2024-01-01", periods=train_rows, freq="min", tz="UTC"
            ),
            "mission_index": np.repeat(np.arange(10), 50),
            "window_index": np.tile(np.arange(50), 10),
            "sample_count": [60] * train_rows,
            "a": rng.normal(0.0, 1.0, train_rows),
            "b": rng.normal(0.0, 1.0, train_rows),
            "c": rng.normal(0.0, 1.0, train_rows),
            **_physical_columns(train_rows),
        }
    )

    timestamps = pd.DatetimeIndex(
        np.concatenate(
            [
                pd.date_range(
                    f"2024-02-{day:02d}T00:00:00Z", periods=60, freq="min"
                ).to_numpy()
                for day in (1, 2, 3)
            ]
        )
    )
    validation_rows = len(timestamps)
    validation = pd.DataFrame(
        {
            "observed_at_utc": timestamps,
            "mission_index": np.repeat(np.arange(6), 30),
            "window_index": np.tile(np.arange(30), 6),
            "sample_count": [60] * validation_rows,
            "a": np.zeros(validation_rows),
            "b": np.zeros(validation_rows),
            "c": np.zeros(validation_rows),
            **_physical_columns(validation_rows),
        }
    )
    for mission in range(6):
        start = mission * 30
        physical = list(range(start, start + 6))
        rare = list(range(start, start + 3))
        validation.loc[physical, [
            "lugging__sum",
            "overload_torque__sum",
            "loaded_high_slip__sum",
            "severe_exposure__sum",
        ]] = 8.0
        validation.loc[rare, ["a", "b", "c"]] = 12.0
    return train, validation


def test_hybrid_threshold_is_derived_from_train_scores_only() -> None:
    train, validation = _candidate_frames()

    first = evaluate_hybrid_candidates(train, validation, _SingleRegime())
    changed_validation = validation.copy()
    changed_validation.loc[:, ["a", "b", "c"]] *= 10.0
    second = evaluate_hybrid_candidates(train, changed_validation, _SingleRegime())

    assert first.accepted and first.model is not None
    assert second.accepted and second.model is not None
    assert first.model.thresholds == second.model.thresholds
