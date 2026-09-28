from pathlib import Path

import pytest

from tractor_usage.application.contracts import WindowProvenance
from tractor_usage.application.operational_telemetry import parse_operational_csv
from tractor_usage.infrastructure.frozen_model import FrozenBundleUsageModel
from tractor_usage.infrastructure.simulated_scenarios import SCENARIOS, scenario_csv
from tractor_usage.infrastructure.window_mapping import complete_window_from_build_result


def _minute() -> str:
    return "\n".join(scenario_csv("aurora-regular").splitlines()[:61]) + "\n"


def test_csv_accepts_new_dates_and_derives_causal_windows():
    parsed = parse_operational_csv(_minute(), "tractor", "simulated_csv")
    assert len(parsed.samples) == 60
    assert parsed.samples[0].observed_at_utc.year == 2026
    assert parsed.preview("simulated_csv")["ready_window_count"] == 1
    assert parsed.windows[0].frame.iloc[0]["severe_exposure__sum"] == 0
    # A file renamed or reformatted retains semantic identity within its machine.
    assert parse_operational_csv(_minute().replace("\n", "\r\n"), "tractor", "simulated_csv").semantic_sha256 == parsed.semantic_sha256
    assert parse_operational_csv(_minute(), "another", "simulated_csv").semantic_sha256 != parsed.semantic_sha256


def test_csv_rejects_invalid_order_gaps_values_and_schema():
    original = _minute()
    rows = original.splitlines()
    invalid = (
        original.replace("2026-09-01T09:00:01Z", "2026-09-01T09:00:00Z"),
        "\n".join([rows[0], *rows[2:]]).replace("2026-09-01T09:00:02Z", "2026-09-01T09:00:03Z"),
        original.replace("1700.0", "NaN", 1),
        original.replace("engine_rpm", "wrong_column", 1),
        original.replace("2026-09-01T09:00:00Z", "2026-09-01T09:00:00"),
    )
    for csv_text in invalid:
        with pytest.raises(ValueError):
            parse_operational_csv(csv_text, "tractor", "simulated_csv")


def test_generated_scenarios_use_real_frozen_model_and_scalar_batch_agree():
    model = FrozenBundleUsageModel.load(Path(__file__).resolve().parents[1] / "models/fendt314-hybrid-v2.0.1")
    results = {}
    for scenario in SCENARIOS:
        parsed = parse_operational_csv(scenario_csv(scenario["id"]), "tractor", "simulated_csv")
        windows = tuple(complete_window_from_build_result(item, provenance=WindowProvenance("simulated_csv", "operational", "test"), telemetry_import_id="test") for item in parsed.windows if item.status == "READY")
        decisions = model.score_many("tractor", windows)
        results[scenario["id"]] = sum(item.hybrid_alert for item in decisions)
        assert len(decisions) == 60
        assert decisions[0] == model.score("tractor", windows[0])
    assert results["aurora-regular"] == 0
    assert all(results[key] > 0 for key in results if key != "aurora-regular")
