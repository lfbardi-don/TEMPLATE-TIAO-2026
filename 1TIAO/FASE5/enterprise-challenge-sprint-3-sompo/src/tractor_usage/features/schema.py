"""Closed feature schema for the usage-context v2 experiment."""

from __future__ import annotations

from collections.abc import Iterable


MODEL_SIGNALS = (
    "engine_rpm",
    "actual_engine_torque_pct",
    "engine_load_pct",
    "accelerator_pct",
    "front_axle_speed_kph",
    "speed_over_ground_mps",
    "ground_implement_speed_mmps",
    "wheel_vehicle_speed_kph",
    "rear_pto_rpm",
    "rear_hitch_position",
    "rear_hitch_in_work",
    "rear_link_force_pct",
    "rear_draft_n",
    "ground_machine_speed_mps",
    "machine_selected_speed_mps",
    "wheel_machine_speed_mps",
    "traction_slip_pct",
    "torque_rise_1s",
    "rpm_change_1s",
    "speed_change_1s",
)

BASE_STATISTICS = ("mean", "std")
TRANSIENT_SIGNALS = frozenset(
    {"torque_rise_1s", "rpm_change_1s", "speed_change_1s"}
)

PROHIBITED_EXACT = frozenset(
    {
        "mission_index",
        "window_index",
        "position_start",
        "position_end",
        "observed_at_utc",
        "calendar_date",
        "split",
        "work_type",
        "implement_model",
        "status",
        "tractor_model",
    }
)

PROHIBITED_PREFIXES = (
    "fuel_",
    "oil_pressure_",
    "coolant_",
    "intake_",
    "ambient_",
    "lugging__",
    "overload_torque__",
    "loaded_high_slip__",
    "thermal_under_load__",
    "harsh_torque_rise__",
    "severe_exposure__",
)


def model_feature_columns(columns: Iterable[str]) -> tuple[str, ...]:
    """Return the v2 model features in deterministic schema order."""

    available = set(columns)
    selected = tuple(
        f"{signal}__{statistic}"
        for signal in MODEL_SIGNALS
        for statistic in (
            (*BASE_STATISTICS, "max")
            if signal in TRANSIENT_SIGNALS
            else BASE_STATISTICS
        )
        if f"{signal}__{statistic}" in available
    )
    if not selected:
        raise ValueError("no usage-context v2 feature columns were found")
    assert_feature_contract(selected)
    return selected


def assert_feature_contract(columns: Iterable[str]) -> None:
    """Reject identifiers, outcomes, health targets, and rule-based audit fields."""

    violations = sorted(
        column
        for column in columns
        if column in PROHIBITED_EXACT
        or column.startswith(PROHIBITED_PREFIXES)
    )
    if violations:
        raise ValueError(f"prohibited model features: {', '.join(violations)}")
