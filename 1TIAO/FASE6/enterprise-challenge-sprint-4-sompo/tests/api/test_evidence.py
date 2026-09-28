from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from tractor_usage.application.checklist import build_inspection_agenda
from tractor_usage.application.contracts import (
    ConflictError,
    Fleet,
    NotFoundError,
    PhysicalDurations,
    ScoredDecision,
    StoredWindow,
    Tractor,
    WindowProvenance,
)
from tractor_usage.application.episodes import derive_episodes, inspection_episodes
from tractor_usage.application.evidence import (
    GetEpisodeDetailUseCase,
    GetExposureTimelineUseCase,
)
from tractor_usage.application.interpretation import exposure_band, regime_labels
from tractor_usage.streaming.replay import RAW_SIGNAL_FIELDS, TelemetrySample


UTC = timezone.utc
IMPORT_ID = "33333333-3333-4333-8333-333333333333"
MISSION_START = datetime(2026, 3, 2, 8, 0, tzinfo=UTC)


def _decision(*, alert: bool, reasons: tuple[str, ...] = ("lugging",)) -> ScoredDecision:
    return ScoredDecision(
        model_version="fendt314-hybrid-v2.0.1",
        operational_regime=0,
        contextual_rarity_score=2.0 if alert else 0.1,
        contextual_rarity_threshold=1.0,
        physical_eligible=alert,
        physical_reasons=reasons if alert else (),
        hybrid_alert=alert,
        contextual_reasons=({"feature": "engine_load_pct__mean", "robust_deviation": 3.0},)
        if alert
        else (),
    )


def _window(
    index: int,
    *,
    alert: bool,
    lugging: float = 0.0,
    at: datetime | None = None,
    reasons: tuple[str, ...] = ("lugging",),
) -> StoredWindow:
    observed = at or MISSION_START + timedelta(seconds=60 * index)
    return StoredWindow(
        id=f"window-{index}-{observed.timestamp()}",
        tractor_id="tractor-1",
        model_version="fendt314-hybrid-v2.0.1",
        mission_index=1,
        window_index=index,
        observed_at_utc=observed,
        sample_count=60,
        span_seconds=59.0,
        window_quality="complete",
        features={},
        physical_durations=PhysicalDurations(lugging, 0, 0, 0, 0, lugging),
        provenance=WindowProvenance("observed_dataset_replay", "validation", "test"),
        evidence_role="operational_output_only",
        idempotency_key=f"key-{index}-{observed.timestamp()}",
        fingerprint="fingerprint",
        decision=_decision(alert=alert, reasons=reasons),
        created_at_utc=observed,
        telemetry_import_id=IMPORT_ID,
    )


def _sample(elapsed: int, *, lugging: bool) -> TelemetrySample:
    values = {field: None for field in RAW_SIGNAL_FIELDS}
    values.update(
        engine_rpm=1200.0 if lugging else 1800.0,
        engine_load_pct=80.0 if lugging else 40.0,
        actual_engine_torque_pct=50.0,
        coolant_temp_c=88.0,
        ground_machine_speed_mps=1.5,
        wheel_machine_speed_mps=1.6,
    )
    return TelemetrySample(
        tractor_id="tractor-1",
        mission_index=1,
        mission_elapsed_seconds=float(elapsed),
        position_seconds=float(elapsed),
        source_row=elapsed,
        observed_at_utc=MISSION_START + timedelta(seconds=elapsed),
        **values,
    )


class _Repository:
    def __init__(self, windows: tuple[StoredWindow, ...]) -> None:
        self.windows = windows
        self.tractor = Tractor(
            "tractor-1", "fleet-1", "T-1", None, "Fendt 314", datetime(2026, 1, 1, tzinfo=UTC)
        )

    def get_tractor(self, tractor_id: str, *, for_update: bool = False):
        return self.tractor if tractor_id == self.tractor.id else None

    def get_fleet_for_tractor(self, tractor_id: str):
        return Fleet("fleet-1", "Frota", datetime(2026, 1, 1, tzinfo=UTC))

    def latest_window_close(self, *, tractor_id=None, fleet_id=None):
        return max(window.observed_at_utc for window in self.windows) + timedelta(seconds=60)

    def list_report_windows(self, tractor_id: str, *, as_of_utc: datetime):
        return self.windows

    def list_history_windows(self, tractor_id: str, *, as_of_utc: datetime):
        return self.windows


class _Model:
    model_version = "fendt314-hybrid-v2.0.1"


class _Samples:
    def __init__(self, samples: tuple[TelemetrySample, ...]) -> None:
        self.samples = samples
        self.requested: dict[str, object] | None = None

    def iter_episode_samples(self, **request):
        self.requested = request
        return iter(self.samples)


def _episode_fixture(*, stored_lugging_in_window_3: float = 10.0):
    windows = (
        _window(2, alert=False),
        _window(3, alert=True, lugging=stored_lugging_in_window_3),
        _window(4, alert=True, lugging=6.0),
    )
    samples = (_sample(179, lugging=True),) + tuple(
        _sample(elapsed, lugging=(elapsed < 190 or 240 <= elapsed < 246))
        for elapsed in range(180, 300)
    )
    return windows, _Samples(samples)


def test_episode_detail_replays_persisted_samples_through_the_ingestion_rules() -> None:
    windows, source = _episode_fixture()
    episode_id = derive_episodes(windows)[0].id

    detail = GetEpisodeDetailUseCase(_Repository(windows), _Model(), source).execute(
        "tractor-1", episode_id
    )

    assert source.requested == {
        "telemetry_import_id": IMPORT_ID,
        "mission_index": 1,
        "first_window_index": 3,
        "last_window_index": 4,
    }
    assert len(detail.samples) == 120
    assert detail.samples[0].observed_at_utc == MISSION_START + timedelta(seconds=180)
    assert detail.samples[0].values["torque_rise_1s"] == 0.0
    assert detail.samples[0].conditions == ("lugging",)
    assert detail.samples[10].conditions == ()
    assert detail.condition_seconds["lugging"] == 16.0
    assert [window.window_index for window in detail.windows] == [3, 4]
    assert [item.id for item in detail.inspection_agenda] == [
        "engine",
        "clutch_transmission",
        "operating_practice",
    ]
    assert detail.regimes == regime_labels("fendt314-hybrid-v2.0.1")


def test_episode_detail_refuses_samples_that_do_not_reproduce_the_scored_window() -> None:
    windows, source = _episode_fixture(stored_lugging_in_window_3=12.0)
    episode_id = derive_episodes(windows)[0].id

    with pytest.raises(ConflictError, match="does not reproduce"):
        GetEpisodeDetailUseCase(_Repository(windows), _Model(), source).execute(
            "tractor-1", episode_id
        )


def test_episode_detail_reports_unknown_episode_as_not_found() -> None:
    windows, source = _episode_fixture()

    with pytest.raises(NotFoundError, match="episode not found"):
        GetEpisodeDetailUseCase(_Repository(windows), _Model(), source).execute(
            "tractor-1", "0" * 20
        )


def test_episode_list_uses_the_same_start_in_horizon_rule_as_the_score() -> None:
    as_of = MISSION_START + timedelta(days=30, seconds=90)
    started_before = _window(0, alert=True, lugging=6.0)
    continued_inside = _window(1, alert=True, lugging=6.0)
    started_inside = replace(
        _window(0, alert=True, lugging=6.0, at=as_of - timedelta(seconds=120)),
        mission_index=2,
    )

    episodes = inspection_episodes(
        derive_episodes((started_before, continued_inside, started_inside)),
        as_of_utc=as_of,
    )

    assert [episode.mission_index for episode in episodes] == [2]


def test_agenda_lists_only_items_triggered_by_observed_conditions() -> None:
    windows = (_window(3, alert=True, lugging=6.0, reasons=("loaded_high_slip",)),)
    episodes = inspection_episodes(
        derive_episodes(windows), as_of_utc=MISSION_START + timedelta(minutes=10)
    )

    agenda = build_inspection_agenda(episodes)

    assert [item.id for item in agenda] == [
        "tires_ballast",
        "axles_front_drive",
        "operating_practice",
    ]
    assert all(item.conditions == ("loaded_high_slip",) for item in agenda)
    assert all(item.episode_ids == (episodes[0].id,) for item in agenda)
    assert build_inspection_agenda(()) == ()


def test_weekly_timeline_keeps_empty_weeks_and_counts_episode_starts() -> None:
    week_one = MISSION_START
    week_three = MISSION_START + timedelta(days=14)
    windows = (
        _window(0, alert=True, lugging=6.0, at=week_one),
        _window(1, alert=True, lugging=6.0, at=week_one + timedelta(seconds=60)),
        _window(2, alert=False, at=week_one + timedelta(seconds=120)),
        replace(_window(0, alert=False, at=week_three), mission_index=2),
    )

    timeline = GetExposureTimelineUseCase(_Repository(windows)).execute("tractor-1")

    assert [week.status for week in timeline.weeks] == ["OK", "NO_DATA", "OK"]
    assert timeline.weeks[0].week_start_utc == datetime(2026, 3, 2, tzinfo=UTC)
    assert timeline.weeks[0].observed_hours == pytest.approx(180 / 3600)
    assert timeline.weeks[0].physical_exposure_seconds == 12.0
    assert timeline.weeks[0].physical_exposure_seconds_per_hour == pytest.approx(12.0 / (180 / 3600))
    assert timeline.weeks[0].alert_windows == 2
    assert timeline.weeks[0].episode_count == 1
    assert timeline.weeks[0].conditions == ("lugging",)
    assert timeline.weeks[0].condition_seconds["lugging"] == 12.0
    assert timeline.weeks[0].condition_episode_counts["lugging"] == 1
    assert timeline.weeks[0].condition_episode_counts["thermal_under_load"] == 0
    assert all(value == 0 for value in timeline.weeks[1].condition_seconds.values())
    assert timeline.weeks[1].physical_exposure_seconds_per_hour is None
    assert timeline.weeks[2].episode_count == 0


def test_exposure_band_thresholds() -> None:
    assert exposure_band(None) is None
    assert exposure_band(24.9) == "BELOW_TYPICAL"
    assert exposure_band(25.0) == "TYPICAL"
    assert exposure_band(74.9) == "TYPICAL"
    assert exposure_band(75.0) == "ABOVE_TYPICAL"
    assert regime_labels("unknown-model") == ()
