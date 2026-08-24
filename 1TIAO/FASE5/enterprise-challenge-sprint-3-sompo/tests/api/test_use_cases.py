from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from tractor_usage.application.contracts import (
    CompleteWindow,
    ConflictError,
    Fleet,
    PhysicalDurations,
    ScoredDecision,
    StoredWindow,
    Tractor,
    WindowProvenance,
)
from tractor_usage.application.episodes import (
    derive_episodes,
    episode_start_keys,
    inspection_episodes,
)
from tractor_usage.application.use_cases import IngestWindowUseCase
from tractor_usage.infrastructure.frozen_model import FrozenBundleUsageModel


UTC = timezone.utc
TELEMETRY_IMPORT_ID = "33333333-3333-4333-8333-333333333333"
SECOND_TELEMETRY_IMPORT_ID = "44444444-4444-4444-8444-444444444444"


class _Repository:
    def __init__(self) -> None:
        self.tractor = Tractor(
            id="tractor-1",
            fleet_id="fleet-1",
            external_id="T-1",
            display_name=None,
            model_name="Fendt 314",
            created_at_utc=datetime(2026, 1, 1, tzinfo=UTC),
        )
        self.windows: list[StoredWindow] = []
        self.authoritative_claim: CompleteWindow | None = None
        self.resolved_window: CompleteWindow | None = None

    @contextmanager
    def transaction(self):
        yield

    def get_tractor(self, tractor_id: str, *, for_update: bool = False):
        return self.tractor if tractor_id == self.tractor.id else None

    def find_window_by_idempotency_key(self, key: str):
        return next((item for item in self.windows if item.idempotency_key == key), None)

    def get_latest_window(self, tractor_id: str):
        return self.windows[-1] if self.windows else None

    def get_latest_window_in_mission(
        self, tractor_id: str, telemetry_import_id: str, mission_index: int
    ):
        matching = [
            item
            for item in self.windows
            if item.telemetry_import_id == telemetry_import_id
            and item.mission_index == mission_index
        ]
        return max(matching, key=lambda item: item.window_index) if matching else None

    def get_mission_provenance(
        self, tractor_id: str, telemetry_import_id: str, mission_index: int
    ):
        matching = [
            item
            for item in self.windows
            if item.telemetry_import_id == telemetry_import_id
            and item.mission_index == mission_index
        ]
        return matching[0].provenance if matching else None

    def resolve_observed_window(self, tractor_id, request):
        if (
            tractor_id != self.tractor.id
            or request.provenance
            != WindowProvenance("observed_dataset_replay", "validation", "test")
        ):
            raise ConflictError("telemetry import lineage conflicts with window provenance")
        if self.authoritative_claim is not None and request != self.authoritative_claim:
            raise ConflictError("submitted window differs from persisted observed telemetry")
        return self.resolved_window or request

    def insert_window(self, tractor_id, request, decision, *, idempotency_key, fingerprint):
        value = StoredWindow(
            id=f"window-{len(self.windows) + 1}",
            tractor_id=tractor_id,
            model_version=decision.model_version,
            mission_index=request.mission_index,
            window_index=request.window_index,
            observed_at_utc=request.observed_at_utc,
            sample_count=request.sample_count,
            span_seconds=request.span_seconds,
            window_quality=request.window_quality,
            features=request.features,
            physical_durations=request.physical_durations,
            provenance=request.provenance,
            evidence_role="operational_output_only",
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
            decision=decision,
            created_at_utc=request.observed_at_utc,
            telemetry_import_id=request.telemetry_import_id,
        )
        self.windows.append(value)
        return value


class _Model:
    model_version = "fendt314-hybrid-v2.0.1"

    def __init__(self) -> None:
        self.calls = 0
        self.windows: list[CompleteWindow] = []

    def score(self, tractor_id, window):
        self.calls += 1
        self.windows.append(window)
        return _decision(alert=False)


def _request(
    *,
    observed_at: datetime,
    window_index: int = 0,
    feature: float = 1.0,
    telemetry_import_id: str = TELEMETRY_IMPORT_ID,
):
    return CompleteWindow(
        mission_index=1,
        window_index=window_index,
        observed_at_utc=observed_at,
        sample_count=60,
        span_seconds=59.0,
        window_quality="complete",
        features={"a": feature},
        physical_durations=PhysicalDurations(0, 0, 0, 0, 0, 0),
        provenance=WindowProvenance("observed_dataset_replay", "validation", "test"),
        telemetry_import_id=telemetry_import_id,
    )


def _decision(*, alert: bool, score: float = 1.0):
    return ScoredDecision(
        model_version="fendt314-hybrid-v2.0.1",
        operational_regime=1,
        contextual_rarity_score=score,
        contextual_rarity_threshold=0.9,
        physical_eligible=alert,
        physical_reasons=("lugging",) if alert else (),
        hybrid_alert=alert,
        contextual_reasons=(
            {"feature": f"feature-{score}", "robust_deviation": score},
        )
        if alert
        else (),
    )


def _window(
    *,
    at: datetime,
    index: int,
    alert: bool,
    mission: int = 1,
    telemetry_import_id: str = TELEMETRY_IMPORT_ID,
) -> StoredWindow:
    return StoredWindow(
        id=f"id-{mission}-{index}-{at.timestamp()}",
        tractor_id="tractor-1",
        model_version="fendt314-hybrid-v2.0.1",
        mission_index=mission,
        window_index=index,
        observed_at_utc=at,
        sample_count=60,
        span_seconds=59.0,
        window_quality="complete",
        features={},
        physical_durations=PhysicalDurations(5, 0, 0, 0, 0, 5),
        provenance=WindowProvenance("observed_dataset_replay", "validation", "test"),
        evidence_role="operational_output_only",
        idempotency_key=f"key-{mission}-{index}-{at.timestamp()}",
        fingerprint="fingerprint",
        decision=_decision(alert=alert),
        created_at_utc=at,
        telemetry_import_id=telemetry_import_id,
    )


def test_ingest_is_durable_idempotent_and_does_not_rescore() -> None:
    repository = _Repository()
    model = _Model()
    use_case = IngestWindowUseCase(repository, model)
    request = _request(observed_at=datetime(2026, 1, 1, tzinfo=UTC))

    first = use_case.execute("tractor-1", request)
    repeated = use_case.execute("tractor-1", request)

    assert first.duplicate is False
    assert repeated.duplicate is True
    assert len(repository.windows) == 1
    assert model.calls == 1


def test_ingest_rejects_conflicting_duplicate_before_rescoring() -> None:
    repository = _Repository()
    model = _Model()
    use_case = IngestWindowUseCase(repository, model)
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    use_case.execute("tractor-1", _request(observed_at=timestamp, feature=1.0))

    with pytest.raises(ConflictError, match="conflicting"):
        use_case.execute("tractor-1", _request(observed_at=timestamp, feature=2.0))

    assert model.calls == 1


def test_ingest_rejects_forged_claim_before_scoring_or_persistence() -> None:
    repository = _Repository()
    model = _Model()
    use_case = IngestWindowUseCase(repository, model)
    observed_at = datetime(2026, 1, 1, tzinfo=UTC)
    repository.authoritative_claim = _request(observed_at=observed_at, feature=1.0)

    with pytest.raises(ConflictError, match="differs from persisted"):
        use_case.execute("tractor-1", _request(observed_at=observed_at, feature=9.0))

    assert model.calls == 0
    assert repository.windows == []


def test_ingest_scores_and_persists_the_resolved_authoritative_window() -> None:
    repository = _Repository()
    model = _Model()
    use_case = IngestWindowUseCase(repository, model)
    request = _request(observed_at=datetime(2026, 1, 1, tzinfo=UTC), feature=1.0)
    authoritative = replace(
        request,
        observed_at_utc=datetime(2026, 1, 1, 0, 1, tzinfo=UTC),
        features={"a": 7.0},
    )
    repository.resolved_window = authoritative

    result = use_case.execute("tractor-1", request)

    assert model.windows == [authoritative]
    assert result.window.observed_at_utc == authoritative.observed_at_utc
    assert result.window.features == authoritative.features


def test_mission_identity_is_scoped_to_the_telemetry_import() -> None:
    repository = _Repository()
    model = _Model()
    use_case = IngestWindowUseCase(repository, model)
    repository.windows.append(
        _window(
            at=datetime(2026, 1, 1, tzinfo=UTC),
            index=9,
            alert=False,
            telemetry_import_id=TELEMETRY_IMPORT_ID,
        )
    )

    result = use_case.execute(
        "tractor-1",
        _request(
            observed_at=datetime(2026, 1, 1, 0, 1, tzinfo=UTC),
            telemetry_import_id=SECOND_TELEMETRY_IMPORT_ID,
        ),
    )

    assert result.duplicate is False
    assert result.window.telemetry_import_id == SECOND_TELEMETRY_IMPORT_ID


def test_episode_derivation_breaks_on_gap_mission_and_non_alert() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    windows = (
        _window(at=start, index=0, alert=True),
        _window(at=start + timedelta(seconds=60), index=1, alert=True),
        _window(at=start + timedelta(seconds=120), index=2, alert=False),
        _window(at=start + timedelta(seconds=180), index=3, alert=True),
        _window(at=start + timedelta(seconds=360), index=4, alert=True),
        _window(at=start + timedelta(seconds=420), index=0, mission=2, alert=True),
    )

    episodes = derive_episodes(windows)

    assert [len(episode.windows) for episode in episodes] == [2, 1, 1, 1]
    assert len(episodes[0].id) == 20


def test_episode_derivation_breaks_between_contiguous_telemetry_imports() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    first = _window(
        at=start,
        index=0,
        alert=True,
        telemetry_import_id=TELEMETRY_IMPORT_ID,
    )
    second = _window(
        at=start + timedelta(seconds=60),
        index=1,
        alert=True,
        telemetry_import_id=SECOND_TELEMETRY_IMPORT_ID,
    )

    episodes = derive_episodes((first, second))
    projection = inspection_episodes(episodes, as_of_utc=start + timedelta(seconds=121))

    assert [len(episode.windows) for episode in episodes] == [1, 1]
    assert episode_start_keys((first, second)) == {
        first.idempotency_key,
        second.idempotency_key,
    }
    assert [(item.started_at_utc, item.ended_at_utc) for item in projection] == [
        (start, start + timedelta(seconds=60)),
        (start + timedelta(seconds=60), start + timedelta(seconds=120)),
    ]


def test_episode_explanation_comes_from_the_most_contextually_rare_window() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    first = _window(at=start, index=0, alert=True)
    second = _window(at=start + timedelta(seconds=60), index=1, alert=True)
    first = replace(first, decision=_decision(alert=True, score=1.5))
    second = replace(second, decision=_decision(alert=True, score=4.0))

    result = inspection_episodes(
        derive_episodes((first, second)),
        as_of_utc=start + timedelta(seconds=121),
    )

    assert len(result) == 1
    assert result[0].maximum_contextual_rarity_score == 4.0
    assert result[0].contextual_reasons == (
        {"feature": "feature-4.0", "robust_deviation": 4.0},
    )


def test_episode_projection_excludes_a_window_that_has_not_closed_at_as_of() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    first = replace(
        _window(at=start, index=0, alert=True),
        decision=_decision(alert=True, score=1.5),
    )
    future = replace(
        _window(at=start + timedelta(seconds=60), index=1, alert=True),
        decision=_decision(alert=True, score=4.0),
    )

    result = inspection_episodes(
        derive_episodes((first, future)),
        as_of_utc=start + timedelta(seconds=90),
    )

    assert len(result) == 1
    assert result[0].ended_at_utc == start + timedelta(seconds=60)
    assert result[0].alerted_seconds == 60.0
    assert result[0].maximum_contextual_rarity_score == 1.5
    assert result[0].contextual_reasons == (
        {"feature": "feature-1.5", "robust_deviation": 1.5},
    )


class _Bundle:
    model_version = "fendt314-hybrid-v2.0.1"
    feature_columns = ("a", "b")

    def __init__(self) -> None:
        self.received = None

    def score_windows(self, frame):
        self.received = frame
        return frame.assign(
            model_version=self.model_version,
            operational_regime=0,
            contextual_rarity_score=1.5,
            contextual_rarity_threshold=1.0,
            physical_eligible=True,
            physical_reasons=[("lugging",)],
            hybrid_alert=True,
            contextual_reasons=[({"feature": "a", "robust_deviation": 2.0},)],
        )


def test_model_adapter_orders_features_and_maps_null_only_at_model_boundary() -> None:
    bundle = _Bundle()
    adapter = FrozenBundleUsageModel(bundle)
    request = CompleteWindow(
        mission_index=0,
        window_index=0,
        observed_at_utc=datetime(2026, 1, 1, tzinfo=UTC),
        sample_count=60,
        span_seconds=59.0,
        window_quality="complete",
        features={"b": 2.0, "a": None},
        physical_durations=PhysicalDurations(5, 0, 0, 0, 0, 5),
        provenance=WindowProvenance("observed_dataset_replay", "validation", "test"),
        telemetry_import_id=TELEMETRY_IMPORT_ID,
    )

    decision = adapter.score("tractor-1", request)

    assert list(bundle.received[["a", "b"]].columns) == ["a", "b"]
    assert bundle.received.loc[0, "a"] != bundle.received.loc[0, "a"]
    assert decision.hybrid_alert is True
