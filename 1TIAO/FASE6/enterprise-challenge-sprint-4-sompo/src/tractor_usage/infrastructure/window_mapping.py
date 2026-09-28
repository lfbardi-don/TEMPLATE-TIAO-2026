"""Pure mapping from a completed causal window to the application contract."""

from __future__ import annotations

from datetime import datetime
import math

import pandas as pd

from tractor_usage.application.contracts import CompleteWindow, PhysicalDurations, WindowProvenance
from tractor_usage.features.schema import BASE_STATISTICS, MODEL_SIGNALS, TRANSIENT_SIGNALS
from tractor_usage.streaming.windows import WindowBuildResult


class WindowMappingError(ValueError):
    """A causal result cannot represent one valid observed API window."""


_FEATURE_KEYS = tuple(
    f"{signal}__{statistic}"
    for signal in MODEL_SIGNALS
    for statistic in (
        (*BASE_STATISTICS, "max") if signal in TRANSIENT_SIGNALS else BASE_STATISTICS
    )
)
_DURATION_COLUMNS = (
    ("lugging", "lugging__sum"),
    ("overload_torque", "overload_torque__sum"),
    ("loaded_high_slip", "loaded_high_slip__sum"),
    ("thermal_under_load", "thermal_under_load__sum"),
    ("harsh_torque_rise", "harsh_torque_rise__sum"),
    ("severe_exposure", "severe_exposure__sum"),
)
_READY_QUALITIES = {"complete", "partial_coverage", "boundary_jitter"}


def complete_window_from_build_result(
    result: WindowBuildResult,
    *,
    provenance: WindowProvenance,
    telemetry_import_id: str,
) -> CompleteWindow:
    """Build the one typed window shared by replay transport and server verification."""

    if result.status != "READY":
        raise WindowMappingError("only READY windows can be mapped")
    if result.quality not in _READY_QUALITIES:
        raise WindowMappingError("READY window has an unsupported quality")
    if result.frame is None or len(result.frame) != 1:
        raise WindowMappingError("READY window must contain exactly one feature row")

    row = result.frame.iloc[0]
    required_columns = (*_FEATURE_KEYS, *(column for _, column in _DURATION_COLUMNS))
    missing = sorted(column for column in required_columns if column not in row.index)
    if missing:
        raise WindowMappingError(
            f"READY window is missing required columns: {', '.join(missing)}"
        )

    features = {key: _optional_finite_float(row[key], key) for key in _FEATURE_KEYS}
    durations = {
        name: _bounded_duration(row[column], column)
        for name, column in _DURATION_COLUMNS
    }
    observed_at = result.observed_at_utc.to_pydatetime()
    if not isinstance(observed_at, datetime):
        raise WindowMappingError("READY window observed timestamp is invalid")
    return CompleteWindow(
        mission_index=result.mission_index,
        window_index=result.window_index,
        observed_at_utc=observed_at,
        sample_count=result.sample_count,
        span_seconds=_finite_float(result.span_seconds, "span_seconds"),
        window_quality=result.quality,
        features=features,
        physical_durations=PhysicalDurations(**durations),
        provenance=provenance,
        telemetry_import_id=telemetry_import_id,
    )


def _optional_finite_float(value: object, name: str) -> float | None:
    if value is None or value is pd.NA:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError) as error:
        raise WindowMappingError(f"{name} must be numeric") from error
    if math.isnan(numeric):
        return None
    if not math.isfinite(numeric):
        raise WindowMappingError(f"{name} must be finite")
    return numeric


def _finite_float(value: object, name: str) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as error:
        raise WindowMappingError(f"{name} must be numeric") from error
    if not math.isfinite(numeric):
        raise WindowMappingError(f"{name} must be finite")
    return numeric


def _bounded_duration(value: object, name: str) -> float:
    duration = _finite_float(value, name)
    if not math.isfinite(duration) or not 0.0 <= duration <= 60.0:
        raise WindowMappingError(f"{name} must be between 0 and 60 seconds")
    return duration
