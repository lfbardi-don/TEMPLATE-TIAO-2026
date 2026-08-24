from __future__ import annotations

from dataclasses import replace
from io import StringIO
import json
import sys
from typing import Iterable
from types import SimpleNamespace

import httpx
import pandas as pd
import pytest

import scripts.run_api_replay as api_replay
from tractor_usage.features.schema import BASE_STATISTICS, MODEL_SIGNALS, TRANSIENT_SIGNALS
from tractor_usage.application.contracts import WindowProvenance
from tractor_usage.infrastructure.http_window_ingest import (
    HttpWindowIngestClient,
    IngestReceipt,
    ObservedReplayProvenance,
    WindowIngestHttpError,
    WindowIngestProtocolError,
    WindowIngestTransportError,
    WindowPayloadMappingError,
    build_complete_window_payload,
)
from tractor_usage.infrastructure.window_mapping import complete_window_from_build_result
from tractor_usage.streaming.replay import FENDT_314_EPOCH_UTC, TelemetrySample
from tractor_usage.streaming.windows import WindowBuildResult


TRACTOR_ID = "8e4aac40-93c2-4b79-88c5-d75b257e7685"
TELEMETRY_IMPORT_ID = "4e4aac40-93c2-4b79-88c5-d75b257e7685"
PROVENANCE = ObservedReplayProvenance(
    dataset_split="validation",
    source_reference="zenodo:14619787#fendt314",
    telemetry_import_id=TELEMETRY_IMPORT_ID,
)
FEATURE_KEYS = tuple(
    f"{signal}__{statistic}"
    for signal in MODEL_SIGNALS
    for statistic in (
        (*BASE_STATISTICS, "max")
        if signal in TRANSIENT_SIGNALS
        else BASE_STATISTICS
    )
)
DURATION_COLUMNS = (
    "lugging__sum",
    "overload_torque__sum",
    "loaded_high_slip__sum",
    "thermal_under_load__sum",
    "harsh_torque_rise__sum",
    "severe_exposure__sum",
)


def _ready_result(*, window_index: int = 0) -> WindowBuildResult:
    frame = pd.DataFrame(
        [
            {
                **{key: 1.5 for key in FEATURE_KEYS},
                **{key: 5.0 for key in DURATION_COLUMNS},
            }
        ]
    )
    return WindowBuildResult(
        status="READY",
        tractor_id=TRACTOR_ID,
        mission_index=277,
        window_index=window_index,
        observed_at_utc=pd.Timestamp("2024-09-01T12:00:00Z"),
        sample_count=60,
        span_seconds=59.0,
        quality="complete",
        frame=frame,
        reason=None,
    )


def _no_data_result() -> WindowBuildResult:
    return WindowBuildResult(
        status="NO_DATA",
        tractor_id=TRACTOR_ID,
        mission_index=277,
        window_index=0,
        observed_at_utc=pd.Timestamp("2024-09-01T12:00:00Z"),
        sample_count=10,
        span_seconds=9.0,
        quality="incomplete",
        frame=None,
        reason="incomplete_60_second_window",
    )


def _sample(second: int) -> TelemetrySample:
    return TelemetrySample(
        tractor_id=TRACTOR_ID,
        mission_index=277,
        mission_elapsed_seconds=float(second),
        position_seconds=float(second),
        source_row=second,
        observed_at_utc=FENDT_314_EPOCH_UTC + pd.to_timedelta(second, unit="s"),
        engine_rpm=1200.0,
        actual_engine_torque_pct=30.0,
        engine_load_pct=60.0,
        accelerator_pct=20.0,
        coolant_temp_c=80.0,
        front_axle_speed_kph=5.0,
        speed_over_ground_mps=2.0,
        ground_implement_speed_mmps=2000.0,
        wheel_vehicle_speed_kph=7.2,
        rear_pto_rpm=500.0,
        rear_hitch_position=40.0,
        rear_hitch_in_work=1.0,
        rear_link_force_pct=10.0,
        rear_draft_n=1000.0,
        ground_machine_speed_mps=2.0,
        machine_selected_speed_mps=2.0,
        wheel_machine_speed_mps=2.0,
    )


def _success_body(*, duplicate: bool, window_index: int = 0) -> dict[str, object]:
    return {
        "duplicate": duplicate,
        "window": {
            "id": "window-1",
            "tractor_id": TRACTOR_ID,
            "model_version": "fendt314-hybrid-v2.0.1",
            "mission_index": 277,
            "window_index": window_index,
            "idempotency_key": "a" * 64,
            "decision": {"hybrid_alert": True},
        },
    }


def _receipt(*, duplicate: bool, window_index: int = 0) -> IngestReceipt:
    return IngestReceipt(
        http_status=200 if duplicate else 201,
        duplicate=duplicate,
        window_id=f"window-{window_index}",
        tractor_id=TRACTOR_ID,
        mission_index=277,
        window_index=window_index,
        idempotency_key="a" * 64,
        model_version="fendt314-hybrid-v2.0.1",
        hybrid_alert=True,
    )


def test_mapper_derives_the_closed_feature_schema_and_observed_provenance() -> None:
    payload = build_complete_window_payload(_ready_result(), PROVENANCE)

    assert len(payload["features"]) == 43
    assert tuple(payload["features"]) == FEATURE_KEYS
    assert payload["physical_durations"] == {
        "lugging": 5.0,
        "overload_torque": 5.0,
        "loaded_high_slip": 5.0,
        "thermal_under_load": 5.0,
        "harsh_torque_rise": 5.0,
        "severe_exposure": 5.0,
    }
    assert payload["observed_at_utc"] == "2024-09-01T12:00:00+00:00"
    assert payload["provenance"] == {
        "source_kind": "observed_dataset_replay",
        "dataset_split": "validation",
        "source_reference": "zenodo:14619787#fendt314",
    }
    assert payload["telemetry_import_id"] == TELEMETRY_IMPORT_ID


def test_http_payload_and_server_reconstruction_share_the_same_window_mapping() -> None:
    result = _ready_result()
    authoritative = complete_window_from_build_result(
        result,
        provenance=WindowProvenance(
            "observed_dataset_replay",
            PROVENANCE.dataset_split,
            PROVENANCE.source_reference,
        ),
        telemetry_import_id=PROVENANCE.telemetry_import_id,
    )

    payload = build_complete_window_payload(result, PROVENANCE)

    assert payload["features"] == dict(authoritative.features)
    assert payload["physical_durations"] == authoritative.physical_durations.as_storage()
    assert payload["observed_at_utc"] == authoritative.observed_at_utc.isoformat()


@pytest.mark.parametrize(
    ("quality", "sample_count", "span_seconds"),
    [
        ("complete", 60, 59.0),
        ("partial_coverage", 55, 54.0),
        ("boundary_jitter", 61, 59.999999),
    ],
)
def test_mapper_preserves_every_ready_window_quality(
    quality: str,
    sample_count: int,
    span_seconds: float,
) -> None:
    result = replace(
        _ready_result(),
        quality=quality,
        sample_count=sample_count,
        span_seconds=span_seconds,
    )

    payload = build_complete_window_payload(result, PROVENANCE)

    assert payload["window_quality"] == quality
    assert payload["sample_count"] == sample_count
    assert payload["span_seconds"] == span_seconds


@pytest.mark.parametrize("invalid_duration", [float("nan"), float("inf"), -0.1, 60.1])
def test_mapper_rejects_non_finite_or_out_of_range_durations(
    invalid_duration: float,
) -> None:
    result = _ready_result()
    assert result.frame is not None
    result.frame.loc[0, "lugging__sum"] = invalid_duration

    with pytest.raises(WindowPayloadMappingError):
        build_complete_window_payload(result, PROVENANCE)


def test_mapper_converts_pandas_missing_values_to_null_and_rejects_invalid_frames() -> None:
    missing = _ready_result()
    assert missing.frame is not None
    missing.frame.loc[0, FEATURE_KEYS[0]] = pd.NA
    missing.frame.loc[0, FEATURE_KEYS[1]] = float("nan")
    payload = build_complete_window_payload(missing, PROVENANCE)
    assert payload["features"][FEATURE_KEYS[0]] is None
    assert payload["features"][FEATURE_KEYS[1]] is None

    infinity = _ready_result()
    assert infinity.frame is not None
    infinity.frame.loc[0, FEATURE_KEYS[0]] = float("inf")
    with pytest.raises(WindowPayloadMappingError, match="finite"):
        build_complete_window_payload(infinity, PROVENANCE)

    original = _ready_result()
    assert original.frame is not None
    absent = WindowBuildResult(
        status=original.status,
        tractor_id=original.tractor_id,
        mission_index=original.mission_index,
        window_index=original.window_index,
        observed_at_utc=original.observed_at_utc,
        sample_count=original.sample_count,
        span_seconds=original.span_seconds,
        quality=original.quality,
        frame=original.frame.drop(columns=[FEATURE_KEYS[0]]),
        reason=original.reason,
    )
    with pytest.raises(WindowPayloadMappingError, match="missing required columns"):
        build_complete_window_payload(absent, PROVENANCE)

    no_data = _no_data_result()
    with pytest.raises(WindowPayloadMappingError, match="only READY"):
        build_complete_window_payload(no_data, PROVENANCE)

    multiple_rows = _ready_result()
    assert multiple_rows.frame is not None
    duplicate_row = pd.concat([multiple_rows.frame, multiple_rows.frame], ignore_index=True)
    multiple_rows = WindowBuildResult(
        status=multiple_rows.status,
        tractor_id=multiple_rows.tractor_id,
        mission_index=multiple_rows.mission_index,
        window_index=multiple_rows.window_index,
        observed_at_utc=multiple_rows.observed_at_utc,
        sample_count=multiple_rows.sample_count,
        span_seconds=multiple_rows.span_seconds,
        quality=multiple_rows.quality,
        frame=duplicate_row,
        reason=multiple_rows.reason,
    )
    with pytest.raises(WindowPayloadMappingError, match="exactly one"):
        build_complete_window_payload(multiple_rows, PROVENANCE)


@pytest.mark.parametrize(("status", "duplicate"), [(201, False), (200, True)])
def test_http_client_posts_once_and_accepts_only_matching_success_receipts(
    status: int,
    duplicate: bool,
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(status, json=_success_body(duplicate=duplicate))

    payload = build_complete_window_payload(_ready_result(), PROVENANCE)
    with httpx.Client(
        base_url="http://127.0.0.1:8000", transport=httpx.MockTransport(handler)
    ) as client:
        receipt = HttpWindowIngestClient(client).ingest(TRACTOR_ID, payload)

    assert len(requests) == 1
    assert requests[0].method == "POST"
    assert requests[0].url.path == f"/v1/tractors/{TRACTOR_ID}/windows"
    assert json.loads(requests[0].content) == payload
    assert receipt.http_status == status
    assert receipt.duplicate is duplicate
    assert receipt.hybrid_alert is True


def test_http_client_fails_without_retry_for_http_transport_and_protocol_errors() -> None:
    payload = build_complete_window_payload(_ready_result(), PROVENANCE)
    http_requests = 0

    def rejected(_: httpx.Request) -> httpx.Response:
        nonlocal http_requests
        http_requests += 1
        return httpx.Response(422, json={"detail": "invalid"})

    with httpx.Client(
        base_url="http://127.0.0.1:8000", transport=httpx.MockTransport(rejected)
    ) as client, pytest.raises(WindowIngestHttpError) as error:
        HttpWindowIngestClient(client).ingest(TRACTOR_ID, payload)
    assert error.value.status_code == 422
    assert http_requests == 1

    transport_requests = 0

    def unavailable(request: httpx.Request) -> httpx.Response:
        nonlocal transport_requests
        transport_requests += 1
        raise httpx.ConnectError("unavailable", request=request)

    with httpx.Client(
        base_url="http://127.0.0.1:8000", transport=httpx.MockTransport(unavailable)
    ) as client, pytest.raises(WindowIngestTransportError):
        HttpWindowIngestClient(client).ingest(TRACTOR_ID, payload)
    assert transport_requests == 1

    def mismatched(_: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json=_success_body(duplicate=True))

    with httpx.Client(
        base_url="http://127.0.0.1:8000", transport=httpx.MockTransport(mismatched)
    ) as client, pytest.raises(WindowIngestProtocolError):
        HttpWindowIngestClient(client).ingest(TRACTOR_ID, payload)

    invalid_identity = _success_body(duplicate=False)
    invalid_identity["window"]["tractor_id"] = "different-tractor"

    with httpx.Client(
        base_url="http://127.0.0.1:8000",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(201, json=invalid_identity)
        ),
    ) as client, pytest.raises(WindowIngestProtocolError, match="tractor"):
        HttpWindowIngestClient(client).ingest(TRACTOR_ID, payload)


class _RecordingAggregator:
    def __init__(self, results_by_source_row: dict[int, tuple[WindowBuildResult, ...]]) -> None:
        self._results_by_source_row = results_by_source_row
        self.ingested: list[int] = []
        self.flush_called = False

    def ingest(self, sample: TelemetrySample) -> tuple[WindowBuildResult, ...]:
        self.ingested.append(sample.source_row)
        return self._results_by_source_row.get(sample.source_row, ())

    def flush(self) -> tuple[WindowBuildResult, ...]:
        self.flush_called = True
        return ()


class _RecordingSender:
    def __init__(self, receipts: Iterable[IngestReceipt] = ()) -> None:
        self._receipts = iter(receipts)
        self.payloads: list[dict[str, object]] = []

    def ingest(self, tractor_id: str, payload: dict[str, object]) -> IngestReceipt:
        assert tractor_id == TRACTOR_ID
        self.payloads.append(payload)
        return next(self._receipts)


class _FailingSender:
    def __init__(self) -> None:
        self.calls = 0

    def ingest(self, _: str, __: dict[str, object]) -> IngestReceipt:
        self.calls += 1
        raise WindowIngestHttpError(503)


def test_run_replay_keeps_no_data_local_delays_each_consumed_sample_and_stops_at_success_limit() -> None:
    aggregator = _RecordingAggregator(
        {
            0: (_no_data_result(),),
            1: (_ready_result(window_index=0),),
            2: (_ready_result(window_index=1),),
        }
    )
    sender = _RecordingSender((_receipt(duplicate=False),))
    output = StringIO()
    sleeps: list[float] = []

    summary = api_replay.run_replay(
        (_sample(second) for second in range(3)),
        aggregator,
        sender,
        PROVENANCE,
        tractor_id=TRACTOR_ID,
        mission_filter=277,
        max_windows=1,
        playback_delay_ms=25.0,
        output=output,
        sleep=sleeps.append,
    )

    records = [json.loads(line) for line in output.getvalue().splitlines()]
    assert [record.get("event") for record in records[:-1]] == [
        "NO_DATA",
        "WINDOW_ACCEPTED",
    ]
    assert summary.stopped_at_limit is True
    assert summary.created_windows == 1
    assert summary.no_data_windows == 1
    assert len(sender.payloads) == 1
    assert aggregator.ingested == [0, 1]
    assert aggregator.flush_called is False
    assert sleeps == [0.025, 0.025]


def test_run_replay_emits_partial_failure_without_flush_or_later_attempts() -> None:
    aggregator = _RecordingAggregator(
        {0: (_ready_result(window_index=0),), 1: (_ready_result(window_index=1),)}
    )
    sender = _FailingSender()
    output = StringIO()

    with pytest.raises(WindowIngestHttpError):
        api_replay.run_replay(
            (_sample(second) for second in range(2)),
            aggregator,
            sender,
            PROVENANCE,
            tractor_id=TRACTOR_ID,
            mission_filter=277,
            max_windows=20,
            playback_delay_ms=0.0,
            output=output,
        )

    records = [json.loads(line) for line in output.getvalue().splitlines()]
    assert aggregator.ingested == [0]
    assert aggregator.flush_called is False
    assert sender.calls == 1
    assert records[-2]["event"] == "ERROR"
    assert records[-2]["http_status"] == 503
    assert records[-2]["mission_index"] == 277
    assert records[-2]["window_index"] == 0
    assert records[-1]["summary"]["status"] == "partial"
    assert records[-1]["summary"]["failures"] == 1


def test_replay_progress_is_notified_after_the_committed_receipt_and_before_visual_delay() -> None:
    aggregator = _RecordingAggregator({0: (_ready_result(window_index=0),)})
    events: list[str] = []

    class Sender:
        def ingest(self, _tractor_id: str, _payload: dict[str, object]) -> IngestReceipt:
            events.append("receipt")
            return _receipt(duplicate=False)

    def observed(progress: api_replay.ReplayRunProgress) -> None:
        assert progress.receipt is not None
        events.append("progress")

    def delayed(seconds: float) -> None:
        assert seconds == 0.025
        events.append("delay")

    summary = api_replay.run_replay(
        [_sample(0)],
        aggregator,
        Sender(),
        PROVENANCE,
        tractor_id=TRACTOR_ID,
        mission_filter=277,
        max_windows=None,
        playback_delay_ms=0.0,
        accepted_window_delay_ms=25.0,
        on_progress=observed,
        sleep=delayed,
        output=StringIO(),
    )

    assert summary.status == "complete"
    assert events == ["receipt", "progress", "delay"]


def test_cli_validates_persisted_import_inputs_and_constructs_a_database_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parsed = api_replay._parser().parse_args(
        [
            "--import-id",
            TRACTOR_ID,
        ]
    )
    assert parsed.max_windows == 20
    assert parsed.api_base_url == "http://127.0.0.1:8000"
    with pytest.raises(SystemExit):
        api_replay._parser().parse_args(
            [
                "--import-id",
                "not-a-uuid",
            ]
        )
    with pytest.raises(SystemExit):
        api_replay._parser().parse_args(
            [
                "--import-id",
                TRACTOR_ID,
                "--api-base-url",
                "https://api.example.test",
            ]
        )

    captured: dict[str, object] = {}

    class Replay:
        def __init__(self, session, import_id, **kwargs) -> None:
            captured["session"] = session
            captured["import_id"] = import_id
            captured.update(kwargs)

        def preflight(self):
            return SimpleNamespace(
                telemetry_import=SimpleNamespace(
                    id=TRACTOR_ID,
                    tractor_id=TRACTOR_ID,
                    dataset_split="validation",
                    semantic_sha256="a" * 64,
                )
            )

        def iter_samples(self):
            return iter(())

    class Engine:
        def dispose(self) -> None:
            captured["disposed"] = True

    class Session:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    class Client:
        def __init__(self, **kwargs) -> None:
            captured["client"] = kwargs

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    def fake_run(*args, **kwargs) -> None:
        captured["run"] = (args, kwargs)

    monkeypatch.setattr(api_replay, "PostgresTelemetryReplay", Replay)
    monkeypatch.setattr(api_replay, "create_database_engine", lambda _: Engine())
    monkeypatch.setattr(api_replay, "create_session_factory", lambda _: lambda: Session())
    monkeypatch.setattr(api_replay.httpx, "Client", Client)
    monkeypatch.setattr(api_replay, "run_replay", fake_run)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_api_replay.py",
            "--import-id",
            TRACTOR_ID,
        ],
    )
    api_replay.main()

    assert captured["import_id"] == TRACTOR_ID
    assert captured["mission_index"] is None
    client_options = captured["client"]
    assert isinstance(client_options, dict)
    assert client_options["base_url"] == "http://127.0.0.1:8000"
    assert client_options["trust_env"] is False
    assert isinstance(client_options["timeout"], httpx.Timeout)
    assert client_options["timeout"].connect == 10.0
    assert captured["disposed"] is True


def test_cli_emits_json_error_when_persisted_import_preflight_fails(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class Replay:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def preflight(self):
            raise api_replay.NotFoundError("telemetry import not found")

    class Engine:
        def dispose(self) -> None:
            pass

    class Session:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    monkeypatch.setattr(api_replay, "PostgresTelemetryReplay", Replay)
    monkeypatch.setattr(api_replay, "create_database_engine", lambda _: Engine())
    monkeypatch.setattr(api_replay, "create_session_factory", lambda _: lambda: Session())
    monkeypatch.setattr(sys, "argv", ["run_api_replay.py", "--import-id", TRACTOR_ID])

    with pytest.raises(SystemExit) as stopped:
        api_replay.main()

    assert stopped.value.code == 1
    assert json.loads(capsys.readouterr().out) == {
        "event": "ERROR",
        "error_class": "NotFoundError",
        "message": "telemetry import not found",
    }
