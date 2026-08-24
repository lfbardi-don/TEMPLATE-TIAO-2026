"""Causal 60-second feature aggregation matching the frozen training schema."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import pandas as pd

from tractor_usage.features.schema import MODEL_SIGNALS, TRANSIENT_SIGNALS
from tractor_usage.streaming.replay import RAW_SIGNAL_FIELDS, TelemetrySample


SIGNAL_RANGES = {
    "engine_rpm": (0.0, 3000.0),
    "actual_engine_torque_pct": (-125.0, 125.0),
    "engine_load_pct": (0.0, 125.0),
    "accelerator_pct": (0.0, 100.0),
    "coolant_temp_c": (-40.0, 150.0),
    "front_axle_speed_kph": (0.0, 80.0),
    "speed_over_ground_mps": (0.0, 30.0),
    "ground_implement_speed_mmps": (0.0, 30000.0),
    "wheel_vehicle_speed_kph": (0.0, 80.0),
    "rear_pto_rpm": (0.0, 1500.0),
    "rear_hitch_position": (0.0, 100.0),
    "rear_hitch_in_work": (0.0, 1.0),
    "rear_link_force_pct": (-100.0, 100.0),
    "rear_draft_n": (-100000.0, 100000.0),
    "ground_machine_speed_mps": (0.0, 30.0),
    "machine_selected_speed_mps": (0.0, 30.0),
    "wheel_machine_speed_mps": (0.0, 30.0),
}

CONDITIONS = (
    "lugging",
    "overload_torque",
    "loaded_high_slip",
    "thermal_under_load",
    "harsh_torque_rise",
)
WINDOW_SPAN_TOLERANCE_SECONDS = 1e-6
WindowQuality = Literal[
    "complete",
    "partial_coverage",
    "boundary_jitter",
    "incomplete",
]


@dataclass(frozen=True)
class WindowBuildResult:
    status: Literal["READY", "NO_DATA"]
    tractor_id: str
    mission_index: int
    window_index: int
    observed_at_utc: pd.Timestamp
    sample_count: int
    span_seconds: float
    quality: WindowQuality
    frame: pd.DataFrame | None
    reason: str | None


@dataclass
class _Accumulator:
    tractor_id: str
    mission_index: int
    window_index: int
    records: list[dict[str, object]] = field(default_factory=list)
    causal_context_complete: bool = True


@dataclass
class _TractorState:
    mission_index: int
    previous_position_seconds: float
    previous_mission_elapsed_seconds: float
    previous_clean: dict[str, float]
    accumulator: _Accumulator


def _clean_value(name: str, value: float | None) -> float:
    if value is None or not np.isfinite(value):
        return np.nan
    minimum, maximum = SIGNAL_RANGES[name]
    return float(value) if minimum <= value <= maximum else np.nan


def _is_true(value: bool) -> bool:
    return bool(value)


def _derived_record(
    sample: TelemetrySample,
    previous_clean: dict[str, float] | None,
) -> tuple[dict[str, object], dict[str, float]]:
    clean = {
        signal: _clean_value(signal, getattr(sample, signal))
        for signal in RAW_SIGNAL_FIELDS
    }
    wheel = clean["wheel_machine_speed_mps"]
    ground = clean["ground_machine_speed_mps"]
    traction_slip = (
        float(np.clip(100.0 * (wheel - ground) / wheel, -100.0, 100.0))
        if np.isfinite(wheel) and np.isfinite(ground) and wheel >= 0.5
        else np.nan
    )
    torque_rise = (
        clean["actual_engine_torque_pct"]
        - previous_clean["actual_engine_torque_pct"]
        if previous_clean is not None
        and np.isfinite(clean["actual_engine_torque_pct"])
        and np.isfinite(previous_clean["actual_engine_torque_pct"])
        else np.nan
    )
    rpm_change = (
        clean["engine_rpm"] - previous_clean["engine_rpm"]
        if previous_clean is not None
        and np.isfinite(clean["engine_rpm"])
        and np.isfinite(previous_clean["engine_rpm"])
        else np.nan
    )
    speed_change = (
        clean["ground_machine_speed_mps"]
        - previous_clean["ground_machine_speed_mps"]
        if previous_clean is not None
        and np.isfinite(clean["ground_machine_speed_mps"])
        and np.isfinite(previous_clean["ground_machine_speed_mps"])
        else np.nan
    )

    rpm = clean["engine_rpm"]
    load = clean["engine_load_pct"]
    torque = clean["actual_engine_torque_pct"]
    coolant = clean["coolant_temp_c"]
    lugging = _is_true(np.isfinite(rpm) and np.isfinite(load) and 600.0 <= rpm < 1400.0 and load > 70.0)
    overload = _is_true(np.isfinite(load) and np.isfinite(torque) and load > 90.0 and torque > 85.0)
    high_slip = _is_true(
        np.isfinite(load)
        and np.isfinite(traction_slip)
        and np.isfinite(ground)
        and load > 50.0
        and traction_slip > 20.0
        and ground >= 0.5
    )
    thermal = _is_true(
        np.isfinite(load)
        and np.isfinite(coolant)
        and load > 70.0
        and coolant >= 95.0
    )
    harsh_rise = _is_true(
        np.isfinite(torque_rise)
        and np.isfinite(load)
        and torque_rise >= 35.0
        and load > 70.0
    )
    conditions = {
        "lugging": lugging,
        "overload_torque": overload,
        "loaded_high_slip": high_slip,
        "thermal_under_load": thermal,
        "harsh_torque_rise": harsh_rise,
    }
    record: dict[str, object] = {
        "observed_at_utc": sample.observed_at_utc,
        "position_seconds": sample.position_seconds,
        **{signal: clean[signal] for signal in MODEL_SIGNALS if signal in clean},
        "traction_slip_pct": traction_slip,
        "torque_rise_1s": torque_rise,
        "rpm_change_1s": rpm_change,
        "speed_change_1s": speed_change,
        **conditions,
        "severe_exposure": any(conditions.values()),
    }
    return record, clean


class CausalWindowAggregator:
    """Own per-tractor causal state and emit closed operational windows."""

    def __init__(self) -> None:
        self._states: dict[str, _TractorState] = {}

    def ingest(self, sample: TelemetrySample) -> tuple[WindowBuildResult, ...]:
        if sample.mission_elapsed_seconds < 0:
            raise ValueError("mission_elapsed_seconds cannot be negative")
        window_index = int(np.floor(sample.mission_elapsed_seconds / 60.0))
        state = self._states.get(sample.tractor_id)
        emitted: list[WindowBuildResult] = []

        if state is None:
            accumulator = _Accumulator(
                sample.tractor_id,
                sample.mission_index,
                window_index,
                causal_context_complete=sample.mission_elapsed_seconds == 0.0,
            )
            record, clean = _derived_record(sample, None)
            accumulator.records.append(record)
            self._states[sample.tractor_id] = _TractorState(
                mission_index=sample.mission_index,
                previous_position_seconds=sample.position_seconds,
                previous_mission_elapsed_seconds=sample.mission_elapsed_seconds,
                previous_clean=clean,
                accumulator=accumulator,
            )
            return ()

        mission_changed = sample.mission_index != state.mission_index
        if sample.position_seconds <= state.previous_position_seconds:
            raise ValueError("sample position must increase per tractor")
        if mission_changed:
            emitted.append(self._finalize(state.accumulator))
            previous_clean = None
        else:
            if sample.mission_elapsed_seconds <= state.previous_mission_elapsed_seconds:
                raise ValueError("mission elapsed time must increase")
            if window_index < state.accumulator.window_index:
                raise ValueError("window index cannot move backwards")
            previous_clean = state.previous_clean
            if window_index != state.accumulator.window_index:
                emitted.append(self._finalize(state.accumulator))

        accumulator = state.accumulator
        if mission_changed or window_index != state.accumulator.window_index:
            accumulator = _Accumulator(
                sample.tractor_id,
                sample.mission_index,
                window_index,
                causal_context_complete=(
                    not mission_changed or sample.mission_elapsed_seconds == 0.0
                ),
            )
        record, clean = _derived_record(sample, previous_clean)
        accumulator.records.append(record)
        self._states[sample.tractor_id] = _TractorState(
            mission_index=sample.mission_index,
            previous_position_seconds=sample.position_seconds,
            previous_mission_elapsed_seconds=sample.mission_elapsed_seconds,
            previous_clean=clean,
            accumulator=accumulator,
        )
        return tuple(emitted)

    def flush(self) -> tuple[WindowBuildResult, ...]:
        results = tuple(
            self._finalize(state.accumulator) for state in self._states.values()
        )
        self._states.clear()
        return results

    def _finalize(self, accumulator: _Accumulator) -> WindowBuildResult:
        records = pd.DataFrame(accumulator.records)
        sample_count = len(records)
        position_start = float(records["position_seconds"].iloc[0])
        position_end = float(records["position_seconds"].iloc[-1])
        span_seconds = position_end - position_start
        observed_at = pd.Timestamp(records["observed_at_utc"].iloc[0])
        standard_window = (
            55 <= sample_count <= 60
            and 54.0 <= span_seconds <= 60.0 + WINDOW_SPAN_TOLERANCE_SECONDS
        )
        boundary_jitter_window = (
            sample_count == 61
            and 59.0 <= span_seconds <= 60.0 + WINDOW_SPAN_TOLERANCE_SECONDS
        )
        if (
            not accumulator.causal_context_complete
            or (not standard_window and not boundary_jitter_window)
        ):
            return WindowBuildResult(
                status="NO_DATA",
                tractor_id=accumulator.tractor_id,
                mission_index=accumulator.mission_index,
                window_index=accumulator.window_index,
                observed_at_utc=observed_at,
                sample_count=sample_count,
                span_seconds=span_seconds,
                quality="incomplete",
                frame=None,
                reason=(
                    "missing_causal_predecessor"
                    if not accumulator.causal_context_complete
                    else "incomplete_60_second_window"
                ),
            )

        quality: WindowQuality
        if boundary_jitter_window:
            quality = "boundary_jitter"
        elif sample_count == 60:
            quality = "complete"
        else:
            quality = "partial_coverage"

        window: dict[str, object] = {
            "tractor_id": accumulator.tractor_id,
            "mission_index": accumulator.mission_index,
            "window_index": accumulator.window_index,
            "sample_count": sample_count,
            "position_start": position_start,
            "position_end": position_end,
            "span_seconds": span_seconds,
            "window_quality": quality,
            "observed_at_utc": observed_at,
        }
        for signal in MODEL_SIGNALS:
            values = pd.to_numeric(records[signal], errors="coerce")
            window[f"{signal}__mean"] = float(values.mean())
            window[f"{signal}__std"] = float(values.std())
            if signal in TRANSIENT_SIGNALS:
                window[f"{signal}__max"] = float(values.max())
        for condition in CONDITIONS:
            window[f"{condition}__sum"] = min(
                60.0,
                float(records[condition].sum()),
            )
        window["severe_exposure__sum"] = min(
            60.0,
            float(records["severe_exposure"].sum()),
        )
        return WindowBuildResult(
            status="READY",
            tractor_id=accumulator.tractor_id,
            mission_index=accumulator.mission_index,
            window_index=accumulator.window_index,
            observed_at_utc=observed_at,
            sample_count=sample_count,
            span_seconds=span_seconds,
            quality=quality,
            frame=pd.DataFrame([window]),
            reason=None,
        )
