"""Read-only evidence views: one episode second by second, and weekly exposure."""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from tractor_usage.application.checklist import build_inspection_agenda
from tractor_usage.application.contracts import (
    ConflictError,
    EpisodeDetail,
    EpisodeSignalSample,
    ExposureTimeline,
    NotFoundError,
    StoredWindow,
    WeeklyExposure,
)
from tractor_usage.application.episodes import (
    closed_episode_windows,
    derive_episodes,
    episode_start_keys,
    project_episode,
)
from tractor_usage.application.interpretation import regime_labels
from tractor_usage.application.ports import (
    EpisodeSampleSource,
    InspectionRepository,
    UsageModel,
)
from tractor_usage.application.use_cases import resolve_as_of
from tractor_usage.streaming.windows import CONDITIONS, derive_sample_record


EPISODE_SIGNALS = (
    "engine_rpm",
    "engine_load_pct",
    "actual_engine_torque_pct",
    "coolant_temp_c",
    "traction_slip_pct",
    "torque_rise_1s",
    "ground_machine_speed_mps",
)
_DURATION_TOLERANCE_SECONDS = 1e-6


class GetEpisodeDetailUseCase:
    def __init__(
        self,
        repository: InspectionRepository,
        model: UsageModel,
        samples: EpisodeSampleSource,
    ) -> None:
        self._repository = repository
        self._model = model
        self._samples = samples

    def execute(
        self, tractor_id: str, episode_id: str, *, as_of_utc: datetime | None = None
    ) -> EpisodeDetail:
        tractor = self._repository.get_tractor(tractor_id)
        if tractor is None:
            raise NotFoundError("tractor not found")
        fleet = self._repository.get_fleet_for_tractor(tractor_id)
        if fleet is None:
            raise NotFoundError("fleet not found")
        as_of = resolve_as_of(self._repository, as_of_utc=as_of_utc, tractor_id=tractor_id)
        windows = self._repository.list_report_windows(tractor_id, as_of_utc=as_of)
        derived = next(
            (episode for episode in derive_episodes(windows) if episode.id == episode_id),
            None,
        )
        closed = closed_episode_windows(derived, as_of_utc=as_of) if derived else ()
        if not closed:
            raise NotFoundError("episode not found")
        episode = project_episode(derived.id, closed)
        samples, condition_seconds = self._replay(closed)
        return EpisodeDetail(
            tractor=tractor,
            fleet=fleet,
            as_of_utc=as_of,
            episode=episode,
            windows=closed,
            samples=samples,
            condition_seconds=condition_seconds,
            regimes=regime_labels(self._model.model_version),
            inspection_agenda=build_inspection_agenda((episode,)),
            provenance=tuple(dict.fromkeys(window.provenance for window in closed)),
        )

    def _replay(
        self, windows: tuple[StoredWindow, ...]
    ) -> tuple[tuple[EpisodeSignalSample, ...], dict[str, float]]:
        first, last = windows[0], windows[-1]
        wanted = {window.window_index for window in windows}
        previous_clean: dict[str, float] | None = None
        per_window: dict[int, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        result: list[EpisodeSignalSample] = []
        for sample in self._samples.iter_episode_samples(
            telemetry_import_id=first.telemetry_import_id,
            mission_index=first.mission_index,
            first_window_index=first.window_index,
            last_window_index=last.window_index,
        ):
            record, clean = derive_sample_record(sample, previous_clean)
            previous_clean = clean
            window_index = int(math.floor(sample.mission_elapsed_seconds / 60.0))
            if window_index not in wanted:
                continue
            signals = {**clean, **record}
            active = tuple(condition for condition in CONDITIONS if record[condition])
            for condition in active:
                per_window[window_index][condition] += 1.0
            if record["severe_exposure"]:
                per_window[window_index]["severe_exposure"] += 1.0
            result.append(
                EpisodeSignalSample(
                    observed_at_utc=sample.observed_at_utc,
                    window_index=window_index,
                    values={name: _finite(signals[name]) for name in EPISODE_SIGNALS},
                    conditions=active,
                )
            )
        for window in windows:
            recomputed = per_window[window.window_index]
            for name, stored in window.physical_durations.as_storage().items():
                if abs(min(60.0, recomputed[name]) - stored) > _DURATION_TOLERANCE_SECONDS:
                    raise ConflictError(
                        "persisted telemetry does not reproduce the scored window"
                    )
        totals = {
            condition: float(
                sum(getattr(window.physical_durations, condition) for window in windows)
            )
            for condition in CONDITIONS
        }
        return tuple(result), totals


class GetExposureTimelineUseCase:
    def __init__(self, repository: InspectionRepository) -> None:
        self._repository = repository

    def execute(
        self, tractor_id: str, *, as_of_utc: datetime | None = None
    ) -> ExposureTimeline:
        tractor = self._repository.get_tractor(tractor_id)
        if tractor is None:
            raise NotFoundError("tractor not found")
        as_of = resolve_as_of(self._repository, as_of_utc=as_of_utc, tractor_id=tractor_id)
        windows = self._repository.list_history_windows(tractor_id, as_of_utc=as_of)
        closed = tuple(
            window
            for window in windows
            if window.observed_at_utc + timedelta(seconds=60) <= as_of
        )
        starts = episode_start_keys(closed)
        episode_conditions = {
            episode.windows[0].idempotency_key: {
                reason for window in episode.windows for reason in window.decision.physical_reasons
            }
            for episode in derive_episodes(closed)
        }
        buckets: dict[datetime, list[StoredWindow]] = defaultdict(list)
        for window in closed:
            buckets[_week_start(window.observed_at_utc + timedelta(seconds=60))].append(window)
        if not buckets:
            return ExposureTimeline(tractor=tractor, as_of_utc=as_of, weeks=())
        weeks: list[WeeklyExposure] = []
        week = min(buckets)
        last_week = _week_start(as_of)
        while week <= last_week:
            weeks.append(_weekly(week, buckets.get(week, []), starts, episode_conditions))
            week += timedelta(days=7)
        return ExposureTimeline(tractor=tractor, as_of_utc=as_of, weeks=tuple(weeks))


def _weekly(
    week_start: datetime, windows: list[StoredWindow], starts: frozenset[str],
    episode_conditions: dict[str, set[str]],
) -> WeeklyExposure:
    if not windows:
        return WeeklyExposure(
            week_start_utc=week_start,
            status="NO_DATA",
            observed_hours=0.0,
            active_days=0,
            physical_exposure_seconds=0.0,
            physical_exposure_seconds_per_hour=None,
            alert_windows=0,
            episode_count=0,
            conditions=(),
            condition_seconds={condition: 0.0 for condition in CONDITIONS},
            condition_episode_counts={condition: 0 for condition in CONDITIONS},
        )
    observed_hours = sum(min(window.sample_count, 60) for window in windows) / 3600.0
    exposure = float(sum(window.physical_durations.severe_exposure for window in windows))
    represented = {
        reason for window in windows for reason in window.decision.physical_reasons
    }
    return WeeklyExposure(
        week_start_utc=week_start,
        status="OK",
        observed_hours=observed_hours,
        active_days=len({window.observed_at_utc.date() for window in windows}),
        physical_exposure_seconds=exposure,
        physical_exposure_seconds_per_hour=exposure / observed_hours if observed_hours else None,
        alert_windows=sum(1 for window in windows if window.decision.hybrid_alert),
        episode_count=sum(1 for window in windows if window.idempotency_key in starts),
        conditions=tuple(condition for condition in CONDITIONS if condition in represented),
        condition_seconds={
            condition: float(sum(getattr(window.physical_durations, condition) for window in windows))
            for condition in CONDITIONS
        },
        condition_episode_counts={
            condition: sum(
                1 for window in windows
                if condition in episode_conditions.get(window.idempotency_key, set())
            )
            for condition in CONDITIONS
        },
    )


def _week_start(value: datetime) -> datetime:
    utc = value.astimezone(timezone.utc)
    monday = utc.date() - timedelta(days=utc.weekday())
    return datetime(monday.year, monday.month, monday.day, tzinfo=timezone.utc)


def _finite(value: object) -> float | None:
    if value is None:
        return None
    number = float(value)
    return number if math.isfinite(number) else None
