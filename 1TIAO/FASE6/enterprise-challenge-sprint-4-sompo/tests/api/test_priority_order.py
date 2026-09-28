from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import get_type_hints

from tractor_usage.application.contracts import (
    Fleet,
    LongitudinalSummary,
    PhysicalDurations,
    ScoredDecision,
    StoredWindow,
    Tractor,
    WindowProvenance,
)
from tractor_usage.application.ports import UsageModel
from tractor_usage.application.use_cases import GetPortfolioPrioritiesUseCase


UTC = timezone.utc
TELEMETRY_IMPORT_ID = "33333333-3333-4333-8333-333333333333"
AS_OF = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)
FLEET = Fleet(id="fleet-1", name="Insured fleet", created_at_utc=AS_OF)


class _ReportingRepository:
    def __init__(
        self,
        tractors: tuple[Tractor, ...],
        windows: dict[str, tuple[StoredWindow, ...]],
    ) -> None:
        self._tractors = tractors
        self._windows = windows

    def list_tractors(self, *, fleet_id: str | None = None):
        if fleet_id is None:
            return self._tractors
        return tuple(tractor for tractor in self._tractors if tractor.fleet_id == fleet_id)

    def get_fleet_for_tractor(self, tractor_id: str):
        return FLEET if any(tractor.id == tractor_id for tractor in self._tractors) else None

    def list_report_windows(self, tractor_id: str, *, as_of_utc: datetime):
        return self._windows.get(tractor_id, ())


class _PriorityModel:
    model_version = "priority-test"

    def __init__(self, values: dict[str, tuple[float, float, str]]) -> None:
        self._values = values

    def aggregate(self, windows, *, as_of_utc):
        tractor_id = windows[0].tractor_id
        current, previous, confidence = self._values[tractor_id]
        score = current if as_of_utc == AS_OF else previous
        return tuple(
            LongitudinalSummary(
                horizon_days=horizon,
                status="OK",
                as_of_utc=as_of_utc,
                observed_hours=1.0,
                active_days=1,
                calendar_coverage=1.0,
                confidence=confidence,
                physical_exposure_seconds_per_hour=1.0,
                alert_exposure_seconds_per_hour=1.0,
                episodes_per_hour=1.0,
                episode_count=1,
                represented_conditions=("lugging",),
                predominant_regimes=(1,),
                component_percentiles={},
                relative_exposure_score=score,
            )
            for horizon in (7, 15, 30)
        )


def _tractor(tractor_id: str, external_id: str) -> Tractor:
    return Tractor(
        id=tractor_id,
        fleet_id=FLEET.id,
        external_id=external_id,
        display_name=None,
        model_name="Fendt 314",
        created_at_utc=AS_OF,
    )


def _alert_window(tractor_id: str, mission_index: int) -> StoredWindow:
    observed_at = AS_OF - timedelta(seconds=60 * mission_index)
    return StoredWindow(
        id=f"window-{tractor_id}-{mission_index}",
        tractor_id=tractor_id,
        model_version="priority-test",
        mission_index=mission_index,
        window_index=0,
        observed_at_utc=observed_at,
        sample_count=60,
        span_seconds=59.0,
        window_quality="complete",
        features={},
        physical_durations=PhysicalDurations(5, 0, 0, 0, 0, 5),
        provenance=WindowProvenance("observed_dataset_replay", "validation", "priority-test"),
        evidence_role="operational_output_only",
        idempotency_key=f"key-{tractor_id}-{mission_index}",
        fingerprint="fingerprint",
        decision=ScoredDecision(
            model_version="priority-test",
            operational_regime=1,
            contextual_rarity_score=2.0,
            contextual_rarity_threshold=1.0,
            physical_eligible=True,
            physical_reasons=("lugging",),
            hybrid_alert=True,
            contextual_reasons=(),
        ),
        created_at_utc=observed_at,
        telemetry_import_id=TELEMETRY_IMPORT_ID,
    )


def test_portfolio_priority_order_covers_tiers_ties_ranks_and_no_data() -> None:
    definitions = (
        ("score-90", "S90"),
        ("trend-10", "T10"),
        ("episodes-2", "E02"),
        ("stable-a", "A"),
        ("stable-b", "B"),
        ("low-confidence", "LOW"),
        ("no-data", "NONE"),
    )
    tractors = tuple(_tractor(*definition) for definition in definitions)
    windows = {
        tractor.id: (_alert_window(tractor.id, 1),)
        for tractor in tractors
        if tractor.id != "no-data"
    }
    windows["episodes-2"] = (
        _alert_window("episodes-2", 2),
        _alert_window("episodes-2", 1),
    )
    model = _PriorityModel(
        {
            "score-90": (90.0, 90.0, "MEDIUM"),
            "trend-10": (80.0, 70.0, "HIGH"),
            "episodes-2": (80.0, 75.0, "HIGH"),
            "stable-a": (80.0, 75.0, "HIGH"),
            "stable-b": (80.0, 75.0, "HIGH"),
            "low-confidence": (100.0, 0.0, "LOW"),
        }
    )

    result = GetPortfolioPrioritiesUseCase(
        _ReportingRepository(tractors, windows), model
    ).execute(as_of_utc=AS_OF)

    assert [priority.tractor.id for priority in result.priorities] == [
        "score-90",
        "trend-10",
        "episodes-2",
        "stable-a",
        "stable-b",
        "low-confidence",
        "no-data",
    ]
    assert [priority.rank for priority in result.priorities] == [1, 2, 3, 4, 5, 6, None]
    assert len(result.priorities[2].episodes_last_30_days) == 2
    assert result.priorities[-1].scores[-1].status == "NO_DATA"


def test_usage_model_protocol_annotations_resolve() -> None:
    assert get_type_hints(UsageModel.aggregate)["return"]
