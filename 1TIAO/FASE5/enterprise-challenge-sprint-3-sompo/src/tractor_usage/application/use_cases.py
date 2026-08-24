"""Use cases coordinating validation-ready values, persistence, and reporting."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json

from tractor_usage.application.contracts import (
    CompleteWindow,
    ConflictError,
    CreateFleet,
    FleetInspectionOverview,
    IngestResult,
    InspectionPriority,
    LongitudinalSummary,
    NotFoundError,
    PortfolioInspectionPriorities,
    StoredWindow,
    TractorInspectionOverview,
    WindowProvenance,
)
from tractor_usage.application.episodes import derive_episodes, inspection_episodes
from tractor_usage.application.ports import InspectionRepository, UsageModel


class CreateFleetUseCase:
    def __init__(self, repository: InspectionRepository) -> None:
        self._repository = repository

    def execute(self, request: CreateFleet):
        with self._repository.transaction():
            return self._repository.create_fleet(request)


class IngestWindowUseCase:
    def __init__(self, repository: InspectionRepository, model: UsageModel) -> None:
        self._repository = repository
        self._model = model

    def execute(self, tractor_id: str, request: CompleteWindow) -> IngestResult:
        with self._repository.transaction():
            tractor = self._repository.get_tractor(tractor_id, for_update=True)
            if tractor is None:
                raise NotFoundError("tractor not found")

            authoritative = self._repository.resolve_observed_window(
                tractor_id, request
            )
            idempotency_key = _idempotency_key(
                self._model.model_version, tractor_id, authoritative
            )
            fingerprint = _fingerprint(authoritative)

            existing = self._repository.find_window_by_idempotency_key(idempotency_key)
            if existing is not None:
                if existing.fingerprint != fingerprint:
                    raise ConflictError("duplicate window identity has conflicting payload")
                return IngestResult(window=existing, duplicate=True)

            latest = self._repository.get_latest_window(tractor_id)
            if latest is not None:
                if authoritative.observed_at_utc <= latest.observed_at_utc:
                    raise ConflictError("window timestamp is out of order")
            mission_latest = self._repository.get_latest_window_in_mission(
                tractor_id,
                authoritative.telemetry_import_id,
                authoritative.mission_index,
            )
            if (
                mission_latest is not None
                and authoritative.window_index <= mission_latest.window_index
            ):
                raise ConflictError("window index is out of order inside mission")

            mission_provenance = self._repository.get_mission_provenance(
                tractor_id,
                authoritative.telemetry_import_id,
                authoritative.mission_index,
            )
            if (
                mission_provenance is not None
                and mission_provenance != authoritative.provenance
            ):
                raise ConflictError("provenance must stay unchanged inside a mission")

            decision = self._model.score(tractor_id, authoritative)
            stored = self._repository.insert_window(
                tractor_id,
                authoritative,
                decision,
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
            )
            return IngestResult(window=stored, duplicate=False)


class GetPortfolioPrioritiesUseCase:
    def __init__(self, repository: InspectionRepository, model: UsageModel) -> None:
        self._repository = repository
        self._model = model

    def execute(self, *, as_of_utc: datetime | None = None) -> PortfolioInspectionPriorities:
        as_of = _resolve_as_of(self._repository, as_of_utc=as_of_utc)
        priorities = _priorities_for_tractors(
            self._repository,
            self._model,
            self._repository.list_tractors(),
            as_of,
        )
        return PortfolioInspectionPriorities(as_of_utc=as_of, priorities=priorities)


class GetFleetOverviewUseCase:
    def __init__(self, repository: InspectionRepository, model: UsageModel) -> None:
        self._repository = repository
        self._model = model

    def execute(
        self, fleet_id: str, *, as_of_utc: datetime | None = None
    ) -> FleetInspectionOverview:
        fleet = self._repository.get_fleet(fleet_id)
        if fleet is None:
            raise NotFoundError("fleet not found")
        as_of = _resolve_as_of(self._repository, as_of_utc=as_of_utc, fleet_id=fleet_id)
        priorities = _priorities_for_tractors(
            self._repository,
            self._model,
            self._repository.list_tractors(fleet_id=fleet_id),
            as_of,
        )
        statuses = {"OK": 0, "NO_DATA": 0}
        for priority in priorities:
            statuses[_score_by_horizon(priority.scores, 30).status] += 1
        return FleetInspectionOverview(
            fleet=fleet,
            as_of_utc=as_of,
            tractor_count=len(priorities),
            status_counts=statuses,
            priorities=priorities,
        )


class GetTractorOverviewUseCase:
    def __init__(self, repository: InspectionRepository, model: UsageModel) -> None:
        self._repository = repository
        self._model = model

    def execute(
        self, tractor_id: str, *, as_of_utc: datetime | None = None
    ) -> TractorInspectionOverview:
        tractor = self._repository.get_tractor(tractor_id)
        if tractor is None:
            raise NotFoundError("tractor not found")
        fleet = self._repository.get_fleet_for_tractor(tractor_id)
        if fleet is None:
            raise NotFoundError("fleet not found")
        as_of = _resolve_as_of(self._repository, as_of_utc=as_of_utc, tractor_id=tractor_id)
        return _tractor_overview(self._repository, self._model, tractor, fleet, as_of)


def _resolve_as_of(
    repository: InspectionRepository,
    *,
    as_of_utc: datetime | None,
    tractor_id: str | None = None,
    fleet_id: str | None = None,
) -> datetime:
    if as_of_utc is not None:
        return _utc(as_of_utc)
    latest = repository.latest_window_close(tractor_id=tractor_id, fleet_id=fleet_id)
    if latest is None:
        raise NotFoundError("inspection history not found")
    return _utc(latest)


def _priorities_for_tractors(repository, model, tractors, as_of):
    unsorted: list[InspectionPriority] = []
    for tractor in tractors:
        fleet = repository.get_fleet_for_tractor(tractor.id)
        if fleet is None:
            raise NotFoundError("fleet not found")
        windows = repository.list_report_windows(tractor.id, as_of_utc=as_of)
        if windows:
            overview = _tractor_overview_from_windows(model, tractor, fleet, as_of, windows)
        else:
            overview = _no_data_overview(tractor, fleet, as_of)
        unsorted.append(
            InspectionPriority(
                rank=None,
                tractor=tractor,
                fleet=fleet,
                as_of_utc=as_of,
                scores=overview.scores,
                previous_30_day_score=overview.previous_30_day_score,
                trend_30_day=overview.trend_30_day,
                episodes_last_30_days=overview.episodes_last_30_days,
                provenance=overview.provenance,
            )
        )
    ordered = sorted(unsorted, key=_priority_sort_key)
    ranked: list[InspectionPriority] = []
    rank = 1
    for priority in ordered:
        score_30 = _score_by_horizon(priority.scores, 30)
        ranked.append(replace(priority, rank=rank if score_30.status == "OK" else None))
        if score_30.status == "OK":
            rank += 1
    return tuple(ranked)


def _tractor_overview(repository, model, tractor, fleet, as_of):
    windows = repository.list_report_windows(tractor.id, as_of_utc=as_of)
    if not windows:
        raise NotFoundError("inspection history not found")
    return _tractor_overview_from_windows(model, tractor, fleet, as_of, windows)


def _tractor_overview_from_windows(model, tractor, fleet, as_of, windows):
    scores = model.aggregate(windows, as_of_utc=as_of)
    previous = model.aggregate(windows, as_of_utc=as_of - timedelta(days=30))
    current_30 = _score_by_horizon(scores, 30)
    previous_30 = _score_by_horizon(previous, 30)
    previous_score = previous_30.relative_exposure_score
    trend = (
        current_30.relative_exposure_score - previous_score
        if current_30.relative_exposure_score is not None and previous_score is not None
        else None
    )
    episodes = inspection_episodes(derive_episodes(windows), as_of_utc=as_of)
    return TractorInspectionOverview(
        tractor=tractor,
        fleet=fleet,
        as_of_utc=as_of,
        scores=scores,
        previous_30_day_score=previous_score,
        trend_30_day=trend,
        episodes_last_30_days=episodes,
        provenance=_distinct_provenance(windows),
    )


def _no_data_overview(tractor, fleet, as_of):
    return TractorInspectionOverview(
        tractor=tractor,
        fleet=fleet,
        as_of_utc=as_of,
        scores=_no_data_summaries(as_of),
        previous_30_day_score=None,
        trend_30_day=None,
        episodes_last_30_days=(),
        provenance=(),
    )


def _no_data_summaries(as_of: datetime) -> tuple[LongitudinalSummary, ...]:
    return tuple(
        LongitudinalSummary(
            horizon_days=horizon,
            status="NO_DATA",
            as_of_utc=as_of,
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
        for horizon in (7, 15, 30)
    )


def _score_by_horizon(
    scores: tuple[LongitudinalSummary, ...], horizon: int
) -> LongitudinalSummary:
    for score in scores:
        if score.horizon_days == horizon:
            return score
    raise RuntimeError(f"model aggregation omitted {horizon}-day score")


def _priority_sort_key(priority: InspectionPriority):
    score = _score_by_horizon(priority.scores, 30)
    if score.status == "NO_DATA":
        tier = 3
    elif score.confidence == "LOW":
        tier = 2
    else:
        tier = 1
    relative_score = score.relative_exposure_score if score.relative_exposure_score is not None else float("-inf")
    trend = priority.trend_30_day if priority.trend_30_day is not None else float("-inf")
    return (
        tier,
        -relative_score,
        -trend,
        -len(priority.episodes_last_30_days),
        priority.fleet.id,
        priority.tractor.external_id,
        priority.tractor.id,
    )


def _distinct_provenance(windows: tuple[StoredWindow, ...]) -> tuple[WindowProvenance, ...]:
    result: list[WindowProvenance] = []
    for window in windows:
        if window.provenance not in result:
            result.append(window.provenance)
    return tuple(result)


def _idempotency_key(model_version: str, tractor_id: str, request: CompleteWindow) -> str:
    material = "|".join(
        (
            model_version,
            tractor_id,
            request.telemetry_import_id,
            str(request.mission_index),
            str(request.window_index),
            _utc(request.observed_at_utc).isoformat(),
        )
    )
    return sha256(material.encode("utf-8")).hexdigest()


def _fingerprint(request: CompleteWindow) -> str:
    payload = {
        "mission_index": request.mission_index,
        "window_index": request.window_index,
        "observed_at_utc": _utc(request.observed_at_utc).isoformat(),
        "sample_count": request.sample_count,
        "span_seconds": request.span_seconds,
        "window_quality": request.window_quality,
        "features": dict(request.features),
        "physical_durations": request.physical_durations.as_storage(),
        "provenance": request.provenance.as_storage(),
        "telemetry_import_id": request.telemetry_import_id,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return sha256(canonical.encode("utf-8")).hexdigest()


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("UTC timestamp is required")
    return value.astimezone(timezone.utc)
