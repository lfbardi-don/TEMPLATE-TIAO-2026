"""Replay observed Fendt telemetry into the local HTTP inspection API."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import ipaddress
import json
import math
import sys
import time
from typing import Callable, Iterable, Literal, TextIO
from urllib.parse import urlparse
from uuid import UUID

import httpx
from sqlalchemy.exc import SQLAlchemyError

from tractor_usage.application.contracts import NotFoundError
from tractor_usage.infrastructure.http_window_ingest import (
    HttpWindowIngestClient,
    IngestReceipt,
    DatasetSplit,
    ObservedReplayProvenance,
    WindowIngestHttpError,
    WindowIngestProtocolError,
    WindowIngestTransportError,
    WindowPayloadMappingError,
    build_complete_window_payload,
)
from tractor_usage.infrastructure.database import Settings, create_database_engine, create_session_factory
from tractor_usage.infrastructure.postgres_telemetry_replay import (
    PostgresTelemetryReplay,
    replay_source_reference,
)
from tractor_usage.streaming.replay import TelemetrySample
from tractor_usage.streaming.windows import CausalWindowAggregator, WindowBuildResult


@dataclass(frozen=True)
class ReplayRunSummary:
    status: Literal["complete", "partial"]
    tractor_id: str
    dataset_split: DatasetSplit
    source_reference: str
    mission_filter: int | None
    samples_replayed: int
    ready_windows: int
    created_windows: int
    duplicate_windows: int
    alert_windows: int
    no_data_windows: int
    failures: int
    stopped_at_limit: bool


@dataclass(frozen=True)
class ReplayRunProgress:
    """One replay observation emitted after a closed window has been handled."""

    summary: ReplayRunSummary
    receipt: IngestReceipt | None


_RUN_FAILURES = (
    WindowPayloadMappingError,
    WindowIngestTransportError,
    WindowIngestHttpError,
    WindowIngestProtocolError,
    ValueError,
    OSError,
    SQLAlchemyError,
    NotFoundError,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--import-id", required=True, type=_import_uuid)
    parser.add_argument("--database-url")
    parser.add_argument("--api-base-url", default="http://127.0.0.1:8000", type=_loopback_http_url)
    parser.add_argument("--mission-index", type=_non_negative_int)
    parser.add_argument("--max-windows", default=20, type=_positive_int)
    parser.add_argument("--playback-delay-ms", default=0.0, type=_non_negative_float)
    parser.add_argument("--timeout-seconds", default=10.0, type=_positive_float)
    return parser


def run_replay(
    samples: Iterable[TelemetrySample],
    aggregator: CausalWindowAggregator,
    sender: HttpWindowIngestClient,
    provenance: ObservedReplayProvenance,
    *,
    tractor_id: str,
    mission_filter: int | None,
    max_windows: int | None,
    playback_delay_ms: float,
    accepted_window_delay_ms: float = 0.0,
    on_progress: Callable[[ReplayRunProgress], None] | None = None,
    output: TextIO = sys.stdout,
    sleep: Callable[[float], None] = time.sleep,
) -> ReplayRunSummary:
    """Send closed READY windows in sample order, with no retry or final flush on stop."""

    if max_windows is not None and max_windows <= 0:
        raise ValueError("max_windows must be positive")
    if playback_delay_ms < 0:
        raise ValueError("playback_delay_ms cannot be negative")
    if accepted_window_delay_ms < 0:
        raise ValueError("accepted_window_delay_ms cannot be negative")

    consumed_samples = 0
    ready_windows = 0
    created_windows = 0
    duplicate_windows = 0
    alert_windows = 0
    no_data_windows = 0
    stopped_at_limit = False
    current_result: WindowBuildResult | None = None

    def summary(
        *, status: Literal["complete", "partial"], failures: int
    ) -> ReplayRunSummary:
        return ReplayRunSummary(
            status=status,
            tractor_id=tractor_id,
            dataset_split=provenance.dataset_split,
            source_reference=provenance.source_reference,
            mission_filter=mission_filter,
            samples_replayed=consumed_samples,
            ready_windows=ready_windows,
            created_windows=created_windows,
            duplicate_windows=duplicate_windows,
            alert_windows=alert_windows,
            no_data_windows=no_data_windows,
            failures=failures,
            stopped_at_limit=stopped_at_limit,
        )

    def handle_result(result: WindowBuildResult) -> bool:
        nonlocal ready_windows
        nonlocal created_windows
        nonlocal duplicate_windows
        nonlocal alert_windows
        nonlocal no_data_windows
        nonlocal stopped_at_limit
        nonlocal current_result

        current_result = result
        if result.tractor_id != tractor_id:
            raise ValueError("causal window tractor does not match the invocation")
        if result.status == "NO_DATA":
            no_data_windows += 1
            _emit(_no_data_event(result), output)
            _notify_progress(on_progress, summary(status="partial", failures=0), None)
            return False

        ready_windows += 1
        payload = build_complete_window_payload(result, provenance)
        receipt = sender.ingest(result.tractor_id, payload)
        created_windows += int(not receipt.duplicate)
        duplicate_windows += int(receipt.duplicate)
        alert_windows += int(receipt.hybrid_alert)
        _emit(_accepted_event(receipt), output)
        # The HTTP client returns only after the API transaction has committed.
        # Presentation observers therefore never see a speculative inference.
        _notify_progress(on_progress, summary(status="partial", failures=0), receipt)
        if accepted_window_delay_ms:
            sleep(accepted_window_delay_ms / 1000.0)
        if max_windows is not None and created_windows + duplicate_windows >= max_windows:
            stopped_at_limit = True
            return True
        return False

    try:
        for sample in samples:
            current_result = None
            if sample.tractor_id != tractor_id:
                raise ValueError("API replay accepts one tractor per invocation")
            consumed_samples += 1
            if playback_delay_ms:
                sleep(playback_delay_ms / 1000.0)
            for result in aggregator.ingest(sample):
                if handle_result(result):
                    completed = summary(status="partial", failures=0)
                    _emit({"summary": asdict(completed)}, output)
                    return completed

        for result in aggregator.flush():
            if handle_result(result):
                completed = summary(status="partial", failures=0)
                _emit({"summary": asdict(completed)}, output)
                return completed
    except _RUN_FAILURES as error:
        _emit(_error_event(error, tractor_id, current_result), output)
        _emit({"summary": asdict(summary(status="partial", failures=1))}, output)
        raise

    completed = summary(status="complete", failures=0)
    _emit({"summary": asdict(completed)}, output)
    return completed


def _no_data_event(result: WindowBuildResult) -> dict[str, object]:
    return {
        "event": "NO_DATA",
        "tractor_id": result.tractor_id,
        "mission_index": result.mission_index,
        "window_index": result.window_index,
        "observed_at_utc": result.observed_at_utc.isoformat(),
        "sample_count": result.sample_count,
        "span_seconds": result.span_seconds,
        "window_quality": result.quality,
        "reason": result.reason,
    }


def _accepted_event(receipt: IngestReceipt) -> dict[str, object]:
    return {
        "event": "WINDOW_ACCEPTED",
        "outcome": "duplicate" if receipt.duplicate else "created",
        "http_status": receipt.http_status,
        "window_id": receipt.window_id,
        "tractor_id": receipt.tractor_id,
        "mission_index": receipt.mission_index,
        "window_index": receipt.window_index,
        "idempotency_key": receipt.idempotency_key,
        "model_version": receipt.model_version,
        "hybrid_alert": receipt.hybrid_alert,
    }


def _notify_progress(
    callback: Callable[[ReplayRunProgress], None] | None,
    progress_summary: ReplayRunSummary,
    receipt: IngestReceipt | None,
) -> None:
    if callback is not None:
        callback(ReplayRunProgress(summary=progress_summary, receipt=receipt))


def _error_event(
    error: Exception,
    tractor_id: str | None,
    result: WindowBuildResult | None = None,
) -> dict[str, object]:
    event: dict[str, object] = {
        "event": "ERROR",
        "error_class": type(error).__name__,
        "message": str(error),
    }
    if isinstance(error, WindowIngestHttpError):
        event["http_status"] = error.status_code
    if tractor_id is not None:
        event["tractor_id"] = tractor_id
    if result is not None:
        event["mission_index"] = result.mission_index
        event["window_index"] = result.window_index
        event["observed_at_utc"] = result.observed_at_utc.isoformat()
    return event


def _emit(value: dict[str, object], output: TextIO) -> None:
    print(json.dumps(value, sort_keys=True, allow_nan=False), file=output)


def _import_uuid(value: str) -> str:
    try:
        return str(UUID(value))
    except ValueError as error:
        raise argparse.ArgumentTypeError("import-id must be a UUID") from error


def _loopback_http_url(value: str) -> str:
    parsed = urlparse(value)
    if (
        parsed.scheme != "http"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
    ):
        raise argparse.ArgumentTypeError("api-base-url must be an HTTP loopback URL")
    try:
        _ = parsed.port
    except ValueError as error:
        raise argparse.ArgumentTypeError("api-base-url must be an HTTP loopback URL") from error
    if parsed.hostname == "localhost":
        host_is_loopback = True
    else:
        try:
            host_is_loopback = ipaddress.ip_address(parsed.hostname).is_loopback
        except ValueError as error:
            raise argparse.ArgumentTypeError(
                "api-base-url must be an HTTP loopback URL"
            ) from error
    if not host_is_loopback:
        raise argparse.ArgumentTypeError("api-base-url must be an HTTP loopback URL")
    return value


def _non_negative_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("value must be a non-negative integer") from error
    if not math.isfinite(parsed) or parsed < 0:
        raise argparse.ArgumentTypeError("value must be a non-negative integer")
    return parsed


def _positive_int(value: str) -> int:
    parsed = _non_negative_int(value)
    if parsed == 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def _non_negative_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("value must be a non-negative number") from error
    if not math.isfinite(parsed) or parsed < 0:
        raise argparse.ArgumentTypeError("value must be a non-negative number")
    return parsed


def _positive_float(value: str) -> float:
    parsed = _non_negative_float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def main() -> None:
    args = _parser().parse_args()
    timeout = httpx.Timeout(args.timeout_seconds)
    replay_started = False
    engine = create_database_engine(
        args.database_url or Settings.from_environment().database_url
    )
    try:
        with create_session_factory(engine)() as session:
            source = PostgresTelemetryReplay(
                session, args.import_id, mission_index=args.mission_index
            )
            preflight = source.preflight()
            provenance = ObservedReplayProvenance(
                dataset_split=preflight.telemetry_import.dataset_split,
                source_reference=replay_source_reference(preflight.telemetry_import),
                telemetry_import_id=preflight.telemetry_import.id,
            )
            with httpx.Client(
                base_url=args.api_base_url,
                timeout=timeout,
                trust_env=False,
            ) as client:
                replay_started = True
                run_replay(
                    source.iter_samples(),
                    CausalWindowAggregator(),
                    HttpWindowIngestClient(client),
                    provenance,
                    tractor_id=preflight.telemetry_import.tractor_id,
                    mission_filter=args.mission_index,
                    max_windows=args.max_windows,
                    playback_delay_ms=args.playback_delay_ms,
                )
    except _RUN_FAILURES as error:
        if not replay_started:
            _emit(_error_event(error, None), sys.stdout)
        raise SystemExit(1) from error
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
