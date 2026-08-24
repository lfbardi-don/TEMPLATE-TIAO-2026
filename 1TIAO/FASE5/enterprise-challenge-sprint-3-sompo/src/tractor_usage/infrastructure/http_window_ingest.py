"""Observed-window HTTP adapter for the local preventive-inspection API."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Literal, TypedDict
from uuid import UUID

import httpx

from tractor_usage.application.contracts import CompleteWindow, WindowProvenance
from tractor_usage.infrastructure.window_mapping import (
    WindowMappingError,
    complete_window_from_build_result,
)
from tractor_usage.streaming.windows import WindowBuildResult


DatasetSplit = Literal["train", "validation"]


class WindowPayloadMappingError(ValueError):
    """A locally built window cannot satisfy the approved HTTP input contract."""


class WindowIngestTransportError(RuntimeError):
    """The one allowed HTTP attempt could not reach the API."""


class WindowIngestHttpError(RuntimeError):
    """The API rejected the request or did not return a success status."""

    def __init__(self, status_code: int) -> None:
        super().__init__(f"window ingest returned HTTP {status_code}")
        self.status_code = status_code


class WindowIngestProtocolError(RuntimeError):
    """A nominally successful API response violated the response contract."""


class PhysicalDurationsPayload(TypedDict):
    lugging: float
    overload_torque: float
    loaded_high_slip: float
    thermal_under_load: float
    harsh_torque_rise: float
    severe_exposure: float


class ObservedReplayProvenancePayload(TypedDict):
    source_kind: Literal["observed_dataset_replay"]
    dataset_split: DatasetSplit
    source_reference: str


class CompleteWindowPayload(TypedDict):
    mission_index: int
    window_index: int
    observed_at_utc: str
    sample_count: int
    span_seconds: float
    window_quality: Literal["complete", "partial_coverage", "boundary_jitter"]
    features: dict[str, float | None]
    physical_durations: PhysicalDurationsPayload
    provenance: ObservedReplayProvenancePayload
    telemetry_import_id: str


@dataclass(frozen=True)
class ObservedReplayProvenance:
    dataset_split: DatasetSplit
    source_reference: str
    telemetry_import_id: str

    def __post_init__(self) -> None:
        if self.dataset_split not in ("train", "validation"):
            raise ValueError("dataset_split must be train or validation")
        if not self.source_reference.strip() or len(self.source_reference) > 512:
            raise ValueError("source_reference must contain 1 to 512 non-blank characters")
        if self.source_reference != self.source_reference.strip():
            raise ValueError("source_reference must not have surrounding whitespace")
        try:
            UUID(self.telemetry_import_id)
        except ValueError as error:
            raise ValueError("telemetry_import_id must be a UUID") from error


@dataclass(frozen=True)
class IngestReceipt:
    http_status: Literal[200, 201]
    duplicate: bool
    window_id: str
    tractor_id: str
    mission_index: int
    window_index: int
    idempotency_key: str
    model_version: str
    hybrid_alert: bool


def build_complete_window_payload(
    result: WindowBuildResult,
    provenance: ObservedReplayProvenance,
) -> CompleteWindowPayload:
    """Map exactly one ready causal window into the immutable API request shape."""

    try:
        window = complete_window_from_build_result(
            result,
            provenance=WindowProvenance(
                source_kind="observed_dataset_replay",
                dataset_split=provenance.dataset_split,
                source_reference=provenance.source_reference,
            ),
            telemetry_import_id=provenance.telemetry_import_id,
        )
    except WindowMappingError as error:
        raise WindowPayloadMappingError(str(error)) from error
    return _payload_from_complete_window(window)


def _payload_from_complete_window(window: CompleteWindow) -> CompleteWindowPayload:
    return {
        "mission_index": window.mission_index,
        "window_index": window.window_index,
        "observed_at_utc": window.observed_at_utc.isoformat(),
        "sample_count": window.sample_count,
        "span_seconds": window.span_seconds,
        "window_quality": window.window_quality,
        "features": dict(window.features),
        "physical_durations": window.physical_durations.as_storage(),
        "provenance": {
            "source_kind": "observed_dataset_replay",
            "dataset_split": window.provenance.dataset_split,
            "source_reference": window.provenance.source_reference,
        },
        "telemetry_import_id": window.telemetry_import_id,
    }


class HttpWindowIngestClient:
    """One-shot synchronous client; the caller owns the supplied HTTP client."""

    def __init__(self, client: httpx.Client) -> None:
        self._client = client

    def ingest(
        self,
        tractor_id: str,
        payload: CompleteWindowPayload,
    ) -> IngestReceipt:
        try:
            response = self._client.post(
                f"/v1/tractors/{tractor_id}/windows",
                json=payload,
            )
        except httpx.TransportError as error:
            raise WindowIngestTransportError("window ingest transport failed") from error

        if response.status_code not in (200, 201):
            raise WindowIngestHttpError(response.status_code)
        return _receipt_from_response(response, tractor_id, payload)


def _receipt_from_response(
    response: httpx.Response,
    tractor_id: str,
    payload: CompleteWindowPayload,
) -> IngestReceipt:
    try:
        body = response.json()
    except json.JSONDecodeError as error:
        raise WindowIngestProtocolError("successful response is not valid JSON") from error
    if not isinstance(body, dict):
        raise WindowIngestProtocolError("successful response must be a JSON object")

    duplicate = body.get("duplicate")
    window = body.get("window")
    if not isinstance(duplicate, bool) or not isinstance(window, dict):
        raise WindowIngestProtocolError("successful response has an invalid receipt shape")
    if response.status_code == 200 and not duplicate:
        raise WindowIngestProtocolError("HTTP 200 response must be a duplicate")
    if response.status_code == 201 and duplicate:
        raise WindowIngestProtocolError("HTTP 201 response must create a window")

    window_id = _required_text(window, "id")
    returned_tractor_id = _required_text(window, "tractor_id")
    model_version = _required_text(window, "model_version")
    idempotency_key = _required_text(window, "idempotency_key")
    mission_index = _required_int(window, "mission_index")
    window_index = _required_int(window, "window_index")
    decision = window.get("decision")
    if not isinstance(decision, dict):
        raise WindowIngestProtocolError("successful response is missing its decision")
    hybrid_alert = decision.get("hybrid_alert")
    if not isinstance(hybrid_alert, bool):
        raise WindowIngestProtocolError("successful response has an invalid hybrid alert")
    if returned_tractor_id != tractor_id:
        raise WindowIngestProtocolError("successful response tractor does not match request")
    if mission_index != payload["mission_index"]:
        raise WindowIngestProtocolError("successful response mission does not match request")
    if window_index != payload["window_index"]:
        raise WindowIngestProtocolError("successful response window does not match request")

    return IngestReceipt(
        http_status=response.status_code,
        duplicate=duplicate,
        window_id=window_id,
        tractor_id=returned_tractor_id,
        mission_index=mission_index,
        window_index=window_index,
        idempotency_key=idempotency_key,
        model_version=model_version,
        hybrid_alert=hybrid_alert,
    )


def _required_text(value: dict[object, object], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item:
        raise WindowIngestProtocolError(f"successful response has invalid {key}")
    return item


def _required_int(value: dict[object, object], key: str) -> int:
    item = value.get(key)
    if not isinstance(item, int) or isinstance(item, bool):
        raise WindowIngestProtocolError(f"successful response has invalid {key}")
    return item
