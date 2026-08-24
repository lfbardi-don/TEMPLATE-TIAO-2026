from __future__ import annotations

import pytest

from tractor_usage.api.schemas import (
    CompleteWindowRequest,
    EXPECTED_FEATURE_KEYS,
    UpdateInspectionCaseRequest,
    replay_progress_response,
)
from tractor_usage.application.contracts import ReplayProgressSnapshot


def _payload() -> dict[str, object]:
    return {
        "mission_index": 0,
        "window_index": 0,
        "observed_at_utc": "2026-01-01T00:00:00-03:00",
        "sample_count": 60,
        "span_seconds": 59.0,
        "window_quality": "complete",
        "features": {key: 0.0 for key in EXPECTED_FEATURE_KEYS},
        "physical_durations": {
            "lugging": 0.0,
            "overload_torque": 0.0,
            "loaded_high_slip": 0.0,
            "thermal_under_load": 0.0,
            "harsh_torque_rise": 0.0,
            "severe_exposure": 0.0,
        },
        "provenance": {
            "source_kind": "observed_dataset_replay",
            "dataset_split": "validation",
            "source_reference": "zenodo:validation",
        },
        "telemetry_import_id": "33333333-3333-4333-8333-333333333333",
    }


def test_complete_window_normalizes_utc_and_preserves_missing_sensor() -> None:
    payload = _payload()
    payload["features"][EXPECTED_FEATURE_KEYS[0]] = None

    request = CompleteWindowRequest.model_validate(payload)

    assert request.observed_at_utc.isoformat() == "2026-01-01T03:00:00+00:00"
    assert request.features[EXPECTED_FEATURE_KEYS[0]] is None


def test_complete_window_rejects_schema_provenance_and_quality_drift() -> None:
    payload = _payload()
    payload["features"].pop(EXPECTED_FEATURE_KEYS[0])
    with pytest.raises(ValueError, match="exactly match"):
        CompleteWindowRequest.model_validate(payload)

    payload = _payload()
    payload["provenance"]["dataset_split"] = None
    with pytest.raises(ValueError):
        CompleteWindowRequest.model_validate(payload)

    payload = _payload()
    payload["provenance"]["source_kind"] = "unsupported_source"
    with pytest.raises(ValueError):
        CompleteWindowRequest.model_validate(payload)

    payload = _payload()
    payload.pop("telemetry_import_id")
    with pytest.raises(ValueError):
        CompleteWindowRequest.model_validate(payload)

    payload = _payload()
    payload["sample_count"] = 61
    with pytest.raises(ValueError, match="do not form a complete window"):
        CompleteWindowRequest.model_validate(payload)


def test_inspection_patch_preserves_omitted_fields_and_tracks_explicit_null() -> None:
    partial = UpdateInspectionCaseRequest.model_validate(
        {"version": 1, "action": "UPDATE", "assignee": "Nova equipe"}
    ).to_contract()
    clear_due_date = UpdateInspectionCaseRequest.model_validate(
        {"version": 2, "action": "UPDATE", "due_date": None}
    ).to_contract()

    assert partial.assignee_present is True
    assert partial.due_date_present is False
    assert clear_due_date.assignee_present is False
    assert clear_due_date.due_date_present is True


def test_replay_progress_schema_keeps_error_details_out_of_the_http_contract() -> None:
    response = replay_progress_response(
        ReplayProgressSnapshot(
            status="failed",
            tractor_id="tractor-id",
            telemetry_import_id="import-id",
            dataset_split="validation",
            source_doi="10.5281/zenodo.14619787",
            source_license="CC-BY-4.0",
            semantic_sha256="a" * 64,
            total_samples=152_561,
            samples_replayed=60,
            ready_windows=1,
            created_windows=1,
            duplicate_windows=0,
            alert_windows=0,
            no_data_windows=0,
            failures=1,
            recent_inferences=(),
            error_code="DEMO_REPLAY_FAILED",
        )
    )

    assert response["error_code"] == "DEMO_REPLAY_FAILED"
    assert "error" not in response
    assert response["recent_inferences"] == []
