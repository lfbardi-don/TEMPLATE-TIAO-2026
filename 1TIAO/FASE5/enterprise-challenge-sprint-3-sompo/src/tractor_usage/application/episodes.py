"""Pure, read-time episode derivation for durable scored windows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from hashlib import sha256

from tractor_usage.application.contracts import InspectionEpisode, StoredWindow


_CONTIGUITY_TOLERANCE = timedelta(seconds=61, microseconds=1)


@dataclass(frozen=True)
class DerivedEpisode:
    id: str
    windows: tuple[StoredWindow, ...]

    @property
    def mission_index(self) -> int:
        return self.windows[0].mission_index


def derive_episodes(windows: tuple[StoredWindow, ...]) -> tuple[DerivedEpisode, ...]:
    """Derive alert runs without persisting episode state.

    Continuity needs the immediately previous accepted window from the same
    telemetry import and mission, with an incrementing index, no temporal gap,
    and another alert. A non-alert window deliberately breaks a run as well.
    """

    ordered = tuple(sorted(windows, key=_window_sort_key))
    episodes: list[DerivedEpisode] = []
    current: list[StoredWindow] = []
    previous: StoredWindow | None = None

    for window in ordered:
        if not window.decision.hybrid_alert:
            if current:
                episodes.append(_finish(current))
                current = []
            previous = window
            continue

        if current and previous is not None and _continues(previous, window):
            current.append(window)
        else:
            if current:
                episodes.append(_finish(current))
            current = [window]
        previous = window

    if current:
        episodes.append(_finish(current))
    return tuple(episodes)


def _window_sort_key(window: StoredWindow) -> tuple[object, ...]:
    return (window.observed_at_utc, window.mission_index, window.window_index, window.id)


def _continues(previous: StoredWindow, current: StoredWindow) -> bool:
    return bool(
        previous.decision.hybrid_alert
        and previous.telemetry_import_id == current.telemetry_import_id
        and previous.mission_index == current.mission_index
        and current.window_index == previous.window_index + 1
        and current.observed_at_utc > previous.observed_at_utc
        and current.observed_at_utc - previous.observed_at_utc <= _CONTIGUITY_TOLERANCE
    )


def _finish(windows: list[StoredWindow]) -> DerivedEpisode:
    first = windows[0]
    episode_id = sha256(
        f"episode|{first.idempotency_key}".encode("utf-8")
    ).hexdigest()[:20]
    return DerivedEpisode(id=episode_id, windows=tuple(windows))


def episode_start_keys(windows: tuple[StoredWindow, ...]) -> frozenset[str]:
    """Return the windows that start an alert episode for longitudinal scoring."""

    return frozenset(
        episode.windows[0].idempotency_key for episode in derive_episodes(windows)
    )


def inspection_episodes(
    episodes: tuple[DerivedEpisode, ...],
    *,
    as_of_utc,
) -> tuple[InspectionEpisode, ...]:
    """Project overlapping 30-day runs to the detail response."""

    start = as_of_utc - timedelta(days=30)
    result: list[InspectionEpisode] = []
    for episode in episodes:
        closed_windows = tuple(
            window
            for window in episode.windows
            if window.observed_at_utc + timedelta(seconds=60) <= as_of_utc
        )
        if not any(
            start < window.observed_at_utc + timedelta(seconds=60)
            for window in closed_windows
        ):
            continue
        ordered = closed_windows
        conditions = _ordered_unique(
            reason for window in ordered for reason in window.decision.physical_reasons
        )
        regimes = _ordered_unique(
            str(window.decision.operational_regime) for window in ordered
        )
        most_rare = max(
            ordered,
            key=lambda window: window.decision.contextual_rarity_score,
        )
        result.append(
            InspectionEpisode(
                id=episode.id,
                mission_index=episode.mission_index,
                started_at_utc=ordered[0].observed_at_utc,
                ended_at_utc=ordered[-1].observed_at_utc + timedelta(seconds=60),
                alerted_seconds=float(sum(min(window.sample_count, 60) for window in ordered)),
                physical_exposure_seconds=float(
                    sum(window.physical_durations.severe_exposure for window in ordered)
                ),
                conditions=conditions,
                operational_regimes=tuple(int(value) for value in regimes),
                maximum_contextual_rarity_score=max(
                    window.decision.contextual_rarity_score for window in ordered
                ),
                contextual_reasons=most_rare.decision.contextual_reasons,
            )
        )
    return tuple(result)


def _ordered_unique(values):
    seen: set[object] = set()
    result: list = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return tuple(result)
