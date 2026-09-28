from pathlib import Path

import pandas as pd
import pytest

from tractor_usage.streaming.replay import (
    CONSUMED_TEST_START_UTC,
    FENDT_314_EPOCH_UTC,
    RAW_SIGNAL_FIELDS,
    CsvTelemetryReplay,
    TelemetrySample,
)
from tractor_usage.streaming.windows import CausalWindowAggregator, WindowQuality


def _sample(
    second: int,
    *,
    tractor_id: str = "tractor-a",
    mission: int = 1,
    mission_elapsed: float | None = None,
    position_seconds: float | None = None,
    torque: float = 10.0,
    load: float = 50.0,
) -> TelemetrySample:
    elapsed = float(second if mission_elapsed is None else mission_elapsed)
    position = float(second if position_seconds is None else position_seconds)
    return TelemetrySample(
        tractor_id=tractor_id,
        mission_index=mission,
        mission_elapsed_seconds=elapsed,
        position_seconds=position,
        source_row=second * 10,
        observed_at_utc=FENDT_314_EPOCH_UTC + pd.to_timedelta(position, unit="s"),
        engine_rpm=1200.0,
        actual_engine_torque_pct=torque,
        engine_load_pct=load,
        accelerator_pct=20.0,
        coolant_temp_c=80.0,
        front_axle_speed_kph=5.0,
        speed_over_ground_mps=2.0,
        ground_implement_speed_mmps=2000.0,
        wheel_vehicle_speed_kph=7.2,
        rear_pto_rpm=500.0,
        rear_hitch_position=40.0,
        rear_hitch_in_work=1.0,
        rear_link_force_pct=10.0,
        rear_draft_n=1000.0,
        ground_machine_speed_mps=2.0,
        machine_selected_speed_mps=2.0,
        wheel_machine_speed_mps=2.0,
    )


def test_causal_window_uses_previous_window_sample_for_transient() -> None:
    aggregator = CausalWindowAggregator()
    emitted = []
    for second in range(120):
        torque = 10.0 if second < 60 else 50.0
        emitted.extend(aggregator.ingest(_sample(second, torque=torque, load=80.0)))
    emitted.extend(aggregator.flush())

    ready = [result for result in emitted if result.status == "READY"]
    assert len(ready) == 2
    assert ready[0].sample_count == 60
    assert ready[1].frame is not None
    assert ready[1].frame.loc[0, "torque_rise_1s__max"] == 40.0
    assert ready[1].frame.loc[0, "harsh_torque_rise__sum"] == 1.0


def test_incomplete_window_is_no_data() -> None:
    aggregator = CausalWindowAggregator()
    for second in range(10):
        aggregator.ingest(_sample(second))

    result = aggregator.flush()[0]

    assert result.status == "NO_DATA"
    assert result.frame is None
    assert result.sample_count == 10
    assert result.quality == "incomplete"


def test_replay_can_start_inside_a_mission_and_scores_the_next_complete_window() -> None:
    aggregator = CausalWindowAggregator()
    emitted = []
    for second in range(30, 120):
        emitted.extend(aggregator.ingest(_sample(second)))
    emitted.extend(aggregator.flush())

    assert [(result.window_index, result.status) for result in emitted] == [
        (0, "NO_DATA"),
        (1, "READY"),
    ]
    assert emitted[0].sample_count == 30
    assert emitted[1].sample_count == 60


def test_replay_starting_on_window_boundary_discards_window_without_predecessor() -> None:
    aggregator = CausalWindowAggregator()
    emitted = []
    for second in range(60, 180):
        emitted.extend(aggregator.ingest(_sample(second, load=80.0, torque=50.0)))
    emitted.extend(aggregator.flush())

    assert [(result.window_index, result.status) for result in emitted] == [
        (1, "NO_DATA"),
        (2, "READY"),
    ]
    assert emitted[0].sample_count == 60
    assert emitted[0].reason == "missing_causal_predecessor"
    assert emitted[1].sample_count == 60


@pytest.mark.parametrize(
    ("sample_count", "expected_quality"),
    [
        (55, "partial_coverage"),
        (59, "partial_coverage"),
        (60, "complete"),
        (61, "boundary_jitter"),
    ],
)
def test_window_quality_accepts_only_approved_sample_counts(
    sample_count: int,
    expected_quality: WindowQuality,
) -> None:
    aggregator = CausalWindowAggregator()
    for second in range(sample_count):
        mission_elapsed = float(second) if second < 60 else 59.999999
        aggregator.ingest(_sample(second, mission_elapsed=mission_elapsed))

    result = aggregator.flush()[0]

    assert result.status == "READY"
    assert result.sample_count == sample_count
    assert result.quality == expected_quality
    assert result.frame is not None
    assert result.frame.loc[0, "window_quality"] == expected_quality


def test_window_quality_rejects_invalid_sample_span_combinations() -> None:
    too_short = CausalWindowAggregator()
    for second in range(54):
        too_short.ingest(_sample(second))
    too_short_result = too_short.flush()[0]

    longer_than_tolerance = CausalWindowAggregator()
    for second in range(61):
        mission_elapsed = float(second) if second < 60 else 59.999999
        position_seconds = float(second) if second < 60 else 60.000002
        longer_than_tolerance.ingest(
            _sample(
                second,
                mission_elapsed=mission_elapsed,
                position_seconds=position_seconds,
            )
        )
    longer_than_tolerance_result = longer_than_tolerance.flush()[0]

    for result in (too_short_result, longer_than_tolerance_result):
        assert result.status == "NO_DATA"
        assert result.frame is None
        assert result.quality == "incomplete"


def test_boundary_jitter_window_caps_physical_durations_at_sixty_seconds() -> None:
    aggregator = CausalWindowAggregator()
    for second in range(61):
        mission_elapsed = float(second) if second < 60 else 59.999999
        aggregator.ingest(_sample(second, mission_elapsed=mission_elapsed, load=80.0))

    result = aggregator.flush()[0]

    assert result.status == "READY"
    assert result.frame is not None
    assert result.frame.loc[0, "lugging__sum"] == 60.0
    assert result.frame.loc[0, "severe_exposure__sum"] == 60.0


def _replay_frame(positions: list[float], missions: list[int]) -> pd.DataFrame:
    values: dict[str, object] = {
        "mission_index": missions,
        "position_seconds": positions,
        "source_row": [index * 10 for index in range(len(positions))],
    }
    for field in RAW_SIGNAL_FIELDS:
        values[field] = [0.0] * len(positions)
    return pd.DataFrame(values)


def test_csv_replay_reconstructs_utc_and_resets_mission_elapsed(tmp_path: Path) -> None:
    path = tmp_path / "samples.csv"
    _replay_frame([10.0, 11.0, 20.0, 21.0], [1, 1, 2, 2]).to_csv(
        path, index=False
    )

    samples = list(CsvTelemetryReplay(path, "tractor-a").iter_samples())

    assert [sample.mission_elapsed_seconds for sample in samples] == [0.0, 1.0, 0.0, 1.0]
    assert samples[0].observed_at_utc == FENDT_314_EPOCH_UTC + pd.Timedelta(seconds=10)


def test_csv_replay_rejects_consumed_test_period(tmp_path: Path) -> None:
    path = tmp_path / "test-period.csv"
    test_position = float(
        (CONSUMED_TEST_START_UTC - FENDT_314_EPOCH_UTC).total_seconds()
    )
    _replay_frame([test_position], [99]).to_csv(path, index=False)

    with pytest.raises(ValueError, match="consumed test period"):
        list(CsvTelemetryReplay(path, "tractor-a").iter_samples())
