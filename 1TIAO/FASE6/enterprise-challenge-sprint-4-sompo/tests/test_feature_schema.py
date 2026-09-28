import pytest

from tractor_usage.features.schema import (
    assert_feature_contract,
    model_feature_columns,
)


def test_model_feature_columns_are_closed_and_ordered() -> None:
    columns = {
        "engine_load_pct__std",
        "engine_rpm__mean",
        "engine_rpm__max",
        "torque_rise_1s__max",
        "fuel_rate_lph__mean",
        "mission_index",
        "lugging__sum",
    }

    assert model_feature_columns(columns) == (
        "engine_rpm__mean",
        "engine_load_pct__std",
        "torque_rise_1s__max",
    )


def test_feature_contract_rejects_outcomes_and_health_targets() -> None:
    with pytest.raises(ValueError, match="prohibited model features"):
        assert_feature_contract(
            ["severe_exposure__sum", "oil_pressure_kpa__mean"]
        )
