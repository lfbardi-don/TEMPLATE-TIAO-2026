import pandas as pd
import pytest

from tractor_usage.modeling.longitudinal import (
    _rates,
    aggregate_integrity_horizons,
    fit_longitudinal_baseline,
)


def _scored_history() -> pd.DataFrame:
    rows = 60
    alerts = [index % 5 == 0 for index in range(rows)]
    frame = pd.DataFrame(
        {
            "observed_at_utc": pd.date_range(
                "2024-01-01T12:00:00Z", periods=rows, freq="D"
            ),
            "sample_count": [3600] * rows,
            "severe_exposure__sum": [20.0 if alert else 5.0 for alert in alerts],
            "hybrid_alert": alerts,
            "hybrid_episode_start": alerts,
            "operational_regime": [index % 3 for index in range(rows)],
            "lugging__sum": [20.0 if alert else 0.0 for alert in alerts],
            "overload_torque__sum": [0.0] * rows,
            "loaded_high_slip__sum": [0.0] * rows,
            "thermal_under_load__sum": [0.0] * rows,
            "harsh_torque_rise__sum": [0.0] * rows,
        }
    )
    return frame


def test_longitudinal_scores_use_only_requested_past_horizon() -> None:
    history = _scored_history()
    baseline = fit_longitudinal_baseline(history)

    scores = aggregate_integrity_horizons(
        history,
        "2024-02-29T23:59:59Z",
        baseline,
    )

    assert [score.horizon_days for score in scores] == [7, 15, 30]
    assert all(score.status == "OK" for score in scores)
    assert all(0.0 <= score.relative_exposure_score <= 100.0 for score in scores)
    assert scores[0].active_days == 7


def test_longitudinal_returns_no_data_instead_of_zero_exposure() -> None:
    history = _scored_history()
    baseline = fit_longitudinal_baseline(history)

    scores = aggregate_integrity_horizons(
        history,
        "2025-01-01T00:00:00Z",
        baseline,
    )

    assert all(score.status == "NO_DATA" for score in scores)
    assert all(score.relative_exposure_score is None for score in scores)


def test_longitudinal_rejects_mixed_tractor_history() -> None:
    baseline = fit_longitudinal_baseline(_scored_history())
    history = _scored_history()
    history["tractor_id"] = "tractor-a"
    history.loc[1, "tractor_id"] = "tractor-b"

    with pytest.raises(ValueError, match="cannot mix tractor"):
        aggregate_integrity_horizons(history, "2024-02-29T23:59:59Z", baseline)


def test_longitudinal_uses_window_close_for_cutoff_membership() -> None:
    baseline = fit_longitudinal_baseline(_scored_history())
    history = _scored_history().iloc[[0]].copy()
    history.loc[:, "observed_at_utc"] = pd.Timestamp("2024-03-01T00:00:00Z")

    before_close = aggregate_integrity_horizons(
        history,
        "2024-03-01T00:00:59Z",
        baseline,
    )
    at_close = aggregate_integrity_horizons(
        history,
        "2024-03-01T00:01:00Z",
        baseline,
    )

    assert all(score.status == "NO_DATA" for score in before_close)
    assert all(score.status == "OK" for score in at_close)


def test_longitudinal_clips_boundary_jitter_to_sixty_effective_seconds() -> None:
    sixty_samples = _scored_history()
    sixty_samples["sample_count"] = 60
    sixty_one_samples = sixty_samples.copy()
    sixty_one_samples["sample_count"] = 61

    assert fit_longitudinal_baseline(sixty_one_samples) == fit_longitudinal_baseline(
        sixty_samples
    )

    boundary_window = sixty_one_samples.iloc[[0]].copy()
    boundary_window.loc[:, "observed_at_utc"] = pd.Timestamp("2024-03-01T00:00:00Z")
    baseline = fit_longitudinal_baseline(sixty_samples)
    scores = aggregate_integrity_horizons(
        boundary_window,
        "2024-03-01T00:01:00Z",
        baseline,
    )

    assert _rates(boundary_window)["physical_exposure_seconds_per_hour"] == pytest.approx(
        1200.0
    )
    assert all(score.observed_hours == pytest.approx(60.0 / 3600.0) for score in scores)


def test_longitudinal_counts_active_days_with_mixed_iso_precision() -> None:
    baseline = fit_longitudinal_baseline(_scored_history())
    history = _scored_history().iloc[:2].copy()
    history["observed_at_utc"] = [
        "2024-03-01T00:00:00+00:00",
        "2024-03-02T00:00:00.100000+00:00",
    ]

    scores = aggregate_integrity_horizons(
        history,
        "2024-03-02T00:01:00.100000+00:00",
        baseline,
    )

    assert all(score.status == "OK" for score in scores)
    assert all(score.active_days == 2 for score in scores)
