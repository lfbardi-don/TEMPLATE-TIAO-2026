"""Run the cloneable, live Fendt 314 observed-validation demonstration."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from hashlib import sha256
import ipaddress
import json
import math
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from typing import Any, Literal
from urllib.error import URLError
from urllib.request import urlopen
from uuid import UUID

import httpx
import psycopg
import uvicorn
from sqlalchemy import event, func, select, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import ArgumentError, SQLAlchemyError

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.run_api_replay import ReplayRunProgress, ReplayRunSummary, run_replay
from tractor_usage.api.app import create_app
from tractor_usage.application.contracts import (
    ConflictError,
    CreateFleet,
    CreateTractor,
    ModelUnavailableError,
    RecentReplayInference,
    ReplayProgressSnapshot,
    TelemetryImport,
)
from tractor_usage.application.telemetry import ImportTelemetryUseCase
from tractor_usage.application.use_cases import CreateFleetUseCase
from tractor_usage.infrastructure.database import (
    Settings,
    create_database_engine,
    create_session_factory,
)
from tractor_usage.infrastructure.http_window_ingest import (
    HttpWindowIngestClient,
    ObservedReplayProvenance,
    WindowIngestHttpError,
    WindowIngestProtocolError,
    WindowIngestTransportError,
    WindowPayloadMappingError,
)
from tractor_usage.infrastructure.models import ScoredWindowRecord
from tractor_usage.infrastructure.postgres_telemetry_replay import (
    PostgresTelemetryReplay,
    replay_source_reference,
)
from tractor_usage.infrastructure.repositories import PostgresInspectionRepository
from tractor_usage.infrastructure.telemetry_files import TelemetryFileError
from tractor_usage.infrastructure.telemetry_repository import PostgresTelemetryRepository
from tractor_usage.streaming.windows import CausalWindowAggregator


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DATASET_DIRECTORY = REPOSITORY_ROOT / "data" / "fendt314-validation"
DATASET_MANIFEST_PATH = DATASET_DIRECTORY / "manifest.json"
MODEL_DIR = REPOSITORY_ROOT / "models" / "fendt314-hybrid-v2.0.1"
MODEL_MANIFEST_PATH = MODEL_DIR / "manifest.json"
DEMO_DIRECTORY = REPOSITORY_ROOT / ".demo-real"
REPLAY_PATH = DEMO_DIRECTORY / "replay.jsonl"
FRONTEND_LOG_PATH = DEMO_DIRECTORY / "frontend.log"
VITE_EXECUTABLE = REPOSITORY_ROOT / "frontend" / "node_modules" / ".bin" / "vite"

DEMO_DATABASE_NAME = "tractor_usage_demo_real"
PRESERVED_DATABASE_NAME = "tractor_usage"
DEMO_DATABASE_URL = (
    "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/tractor_usage_demo_real"
)
API_BASE_URL = "http://127.0.0.1:8010"
FRONTEND_BASE_URL = "http://127.0.0.1:5174"

EXPECTED_DATASET_FILE_NAME = "fendt314-validation-observed.csv.gz"
EXPECTED_DATASET_SIZE_BYTES = 6_627_620
EXPECTED_DATASET_SHA256 = "7cce02f2ee53dadd24cac7d0280462e843844ca4000cdc778df4e47f5dca4be1"
EXPECTED_SEMANTIC_SHA256 = "d876974fdbf7a8053038ef652bea027783291f5321fae029a411ba21ce6e390c"
EXPECTED_SAMPLE_COUNT = 152_561
EXPECTED_MISSION_COUNT = 105
EXPECTED_SOURCE_DOI = "10.5281/zenodo.14619787"
EXPECTED_SOURCE_LICENSE = "CC-BY-4.0"
EXPECTED_MODEL_VERSION = "fendt314-hybrid-v2.0.1"


class DemoRealError(RuntimeError):
    """A safe, actionable failure in the isolated local demo workflow."""


@dataclass(frozen=True)
class ObservedDatasetManifest:
    source_path: Path
    dataset_split: Literal["validation"]
    source_doi: str
    source_license: str
    size_bytes: int
    byte_sha256: str
    semantic_sha256: str
    sample_count: int
    mission_count: int
    started_at_utc: str
    ended_at_utc: str


@dataclass(frozen=True)
class InitializedDemo:
    engine: Engine
    fleet_id: str
    tractor_id: str
    telemetry_import: TelemetryImport
    model_version: str


class InMemoryReplayProgress:
    """Invocation-local, lock-protected state read by the Uvicorn server thread."""

    def __init__(self, demo: InitializedDemo, source: ObservedDatasetManifest) -> None:
        self._lock = threading.Lock()
        self._snapshot = ReplayProgressSnapshot(
            status="waiting",
            tractor_id=demo.tractor_id,
            telemetry_import_id=demo.telemetry_import.id,
            dataset_split=demo.telemetry_import.dataset_split,
            source_doi=source.source_doi,
            source_license=source.source_license,
            semantic_sha256=source.semantic_sha256,
            total_samples=source.sample_count,
            samples_replayed=0,
            ready_windows=0,
            created_windows=0,
            duplicate_windows=0,
            alert_windows=0,
            no_data_windows=0,
            failures=0,
            recent_inferences=(),
            error_code=None,
        )

    def snapshot(self) -> ReplayProgressSnapshot:
        with self._lock:
            return self._snapshot

    def start(self) -> None:
        with self._lock:
            if self._snapshot.status != "waiting":
                raise DemoRealError("demo replay cannot start more than once")
            self._snapshot = replace(self._snapshot, status="running")

    def observe(self, progress: ReplayRunProgress) -> None:
        with self._lock:
            if self._snapshot.status != "running":
                raise DemoRealError("demo replay progress was reported outside the running state")
            summary = progress.summary
            self._require_monotonic(summary)
            recent = self._snapshot.recent_inferences
            if progress.receipt is not None:
                recent = (
                    *recent,
                    RecentReplayInference(
                        mission_index=progress.receipt.mission_index,
                        window_index=progress.receipt.window_index,
                        model_version=progress.receipt.model_version,
                        hybrid_alert=progress.receipt.hybrid_alert,
                    ),
                )[-8:]
            self._snapshot = replace(
                self._snapshot,
                samples_replayed=summary.samples_replayed,
                ready_windows=summary.ready_windows,
                created_windows=summary.created_windows,
                duplicate_windows=summary.duplicate_windows,
                alert_windows=summary.alert_windows,
                no_data_windows=summary.no_data_windows,
                failures=summary.failures,
                recent_inferences=recent,
            )

    def complete(self, summary: ReplayRunSummary) -> None:
        with self._lock:
            if self._snapshot.status != "running" or summary.status != "complete":
                raise DemoRealError("demo replay cannot complete from its current state")
            self._require_monotonic(summary)
            self._snapshot = replace(
                self._snapshot,
                status="complete",
                samples_replayed=summary.samples_replayed,
                ready_windows=summary.ready_windows,
                created_windows=summary.created_windows,
                duplicate_windows=summary.duplicate_windows,
                alert_windows=summary.alert_windows,
                no_data_windows=summary.no_data_windows,
                failures=summary.failures,
            )

    def fail(self) -> None:
        with self._lock:
            if self._snapshot.status == "complete":
                raise DemoRealError("completed demo replay cannot be marked failed")
            if self._snapshot.status != "failed":
                self._snapshot = replace(
                    self._snapshot,
                    status="failed",
                    failures=max(1, self._snapshot.failures),
                    error_code="DEMO_REPLAY_FAILED",
                )

    def _require_monotonic(self, summary: ReplayRunSummary) -> None:
        current = self._snapshot
        values = (
            (summary.samples_replayed, current.samples_replayed),
            (summary.ready_windows, current.ready_windows),
            (summary.created_windows, current.created_windows),
            (summary.duplicate_windows, current.duplicate_windows),
            (summary.alert_windows, current.alert_windows),
            (summary.no_data_windows, current.no_data_windows),
            (summary.failures, current.failures),
        )
        if any(candidate < previous for candidate, previous in values):
            raise DemoRealError("demo replay counters must be monotonic")


def validate_demo_database_url(value: str) -> str:
    """Allow only the literal isolated PostgreSQL sibling database."""

    try:
        parsed = make_url(value)
    except (ArgumentError, ValueError) as error:
        raise DemoRealError("demo database URL is invalid") from error
    try:
        loopback = bool(parsed.host and ipaddress.ip_address(parsed.host).is_loopback)
    except ValueError:
        loopback = False
    if (
        parsed.drivername != "postgresql+psycopg"
        or not loopback
        or parsed.port != 5432
        or parsed.username != "postgres"
        or parsed.database != DEMO_DATABASE_NAME
        or parsed.query
    ):
        raise DemoRealError(
            "demo database must be PostgreSQL/psycopg as postgres on loopback:5432 "
            f"with database {DEMO_DATABASE_NAME}"
        )
    return value


def load_observed_dataset_manifest(
    manifest_path: Path = DATASET_MANIFEST_PATH,
) -> ObservedDatasetManifest:
    """Load source identity only; it deliberately contains no scored outputs."""

    raw = _load_json_object(manifest_path, "observed dataset manifest")
    if raw.get("schema_version") != "observed-demo-source-v1":
        raise DemoRealError("observed dataset manifest has an unsupported schema version")
    source_path = _safe_relative_source_path(manifest_path, _text(raw.get("file_name"), "file_name"))
    dataset_split = _text(raw.get("dataset_split"), "dataset_split")
    if dataset_split != "validation":
        raise DemoRealError("observed dataset manifest identity differs from the approved source")
    source = ObservedDatasetManifest(
        source_path=source_path,
        dataset_split="validation",
        source_doi=_text(raw.get("source_doi"), "source_doi"),
        source_license=_text(raw.get("source_license"), "source_license"),
        size_bytes=_positive_integer(raw.get("size_bytes"), "size_bytes"),
        byte_sha256=_sha256_text(raw.get("byte_sha256"), "byte_sha256"),
        semantic_sha256=_sha256_text(raw.get("semantic_sha256"), "semantic_sha256"),
        sample_count=_positive_integer(raw.get("sample_count"), "sample_count"),
        mission_count=_positive_integer(raw.get("mission_count"), "mission_count"),
        started_at_utc=_utc_text(raw.get("started_at_utc"), "started_at_utc"),
        ended_at_utc=_utc_text(raw.get("ended_at_utc"), "ended_at_utc"),
    )
    expected = (
        source.source_path.name == EXPECTED_DATASET_FILE_NAME
        and source.source_doi == EXPECTED_SOURCE_DOI
        and source.source_license == EXPECTED_SOURCE_LICENSE
        and source.size_bytes == EXPECTED_DATASET_SIZE_BYTES
        and source.byte_sha256 == EXPECTED_DATASET_SHA256
        and source.semantic_sha256 == EXPECTED_SEMANTIC_SHA256
        and source.sample_count == EXPECTED_SAMPLE_COUNT
        and source.mission_count == EXPECTED_MISSION_COUNT
    )
    if not expected:
        raise DemoRealError("observed dataset manifest identity differs from the approved source")
    if source.ended_at_utc <= source.started_at_utc:
        raise DemoRealError("observed dataset manifest interval is invalid")
    return source


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the local live replay from the bundled observed validation source."
    )
    parser.add_argument("--window-delay-ms", default=20.0, type=_non_negative_float)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--exit-after-replay", action="store_true")
    return parser


def _preflight() -> ObservedDatasetManifest:
    source = load_observed_dataset_manifest()
    if not source.source_path.is_file():
        raise DemoRealError("bundled observed telemetry source is missing")
    if source.source_path.stat().st_size != source.size_bytes:
        raise DemoRealError("bundled observed telemetry source size differs from its manifest")
    if _file_sha256(source.source_path) != source.byte_sha256:
        raise DemoRealError("bundled observed telemetry source checksum differs from its manifest")
    _validate_model_bundle()
    if not VITE_EXECUTABLE.is_file():
        raise DemoRealError("frontend dependencies are missing; run `npm --prefix frontend ci` once")
    for port in (8010, 5174):
        _require_port_free(port)
    return source


def _validate_model_bundle() -> None:
    manifest = _load_json_object(MODEL_MANIFEST_PATH, "frozen model manifest")
    if manifest.get("model_version") != EXPECTED_MODEL_VERSION:
        raise DemoRealError("frozen model version does not match the approved demo identity")
    bundle_name = _text(manifest.get("artifact_filename"), "model bundle filename")
    if Path(bundle_name).name != bundle_name:
        raise DemoRealError("model bundle filename must not escape its directory")
    bundle_path = MODEL_DIR / bundle_name
    if not bundle_path.is_file():
        raise DemoRealError("frozen model bundle is missing")
    if bundle_path.stat().st_size != _positive_integer(
        manifest.get("artifact_size_bytes"), "model bundle size"
    ):
        raise DemoRealError("frozen model bundle size differs from its manifest")
    if _file_sha256(bundle_path) != _sha256_text(
        manifest.get("artifact_sha256"), "model bundle checksum"
    ):
        raise DemoRealError("frozen model bundle checksum differs from its manifest")


def _require_port_free(port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind(("127.0.0.1", port))
        except OSError as error:
            raise DemoRealError(
                f"demo port {port} is already in use; existing processes were not changed"
            ) from error


def _psycopg_parameters(database: str) -> dict[str, object]:
    parsed = make_url(validate_demo_database_url(DEMO_DATABASE_URL))
    return {
        "host": parsed.host,
        "port": parsed.port,
        "user": parsed.username,
        "password": parsed.password,
        "dbname": database,
        "connect_timeout": 5,
    }


def _recreate_demo_database() -> None:
    """Recreate only the literal demo sibling and prove the primary OID stayed fixed."""

    with psycopg.connect(**_psycopg_parameters("postgres"), autocommit=True) as connection:
        _require_psycopg_database(connection, "postgres")
        with connection.cursor() as cursor:
            preserved_oid_before = _database_oid(cursor, PRESERVED_DATABASE_NAME)
            cursor.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (DEMO_DATABASE_NAME,),
            )
            cursor.fetchall()
            cursor.execute("DROP DATABASE IF EXISTS tractor_usage_demo_real")
            cursor.execute("CREATE DATABASE tractor_usage_demo_real")
            preserved_oid_after = _database_oid(cursor, PRESERVED_DATABASE_NAME)
        if preserved_oid_before != preserved_oid_after:
            raise DemoRealError("primary tractor_usage database identity changed unexpectedly")

    with psycopg.connect(
        **_psycopg_parameters(DEMO_DATABASE_NAME), autocommit=True
    ) as connection:
        _require_psycopg_database(connection, DEMO_DATABASE_NAME)


def _require_psycopg_database(connection: psycopg.Connection[Any], expected: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_database()")
        row = cursor.fetchone()
    if row is None or row[0] != expected:
        raise DemoRealError(f"connected PostgreSQL database is not the required {expected}")


def _database_oid(cursor: psycopg.Cursor[Any], database_name: str) -> int:
    cursor.execute("SELECT oid FROM pg_database WHERE datname = %s", (database_name,))
    row = cursor.fetchone()
    if row is None or isinstance(row[0], bool) or not isinstance(row[0], int):
        raise DemoRealError(f"required PostgreSQL database is missing: {database_name}")
    return row[0]


def _run_migrations() -> None:
    environment = os.environ.copy()
    environment["DATABASE_URL"] = validate_demo_database_url(DEMO_DATABASE_URL)
    try:
        subprocess.run(
            ["uv", "run", "alembic", "upgrade", "head"],
            cwd=REPOSITORY_ROOT,
            env=environment,
            check=True,
        )
    except FileNotFoundError as error:
        raise DemoRealError("uv is unavailable; run the documented prerequisites first") from error
    except subprocess.CalledProcessError as error:
        raise DemoRealError("Alembic migration failed for the isolated demo database") from error


def _create_verified_demo_engine() -> Engine:
    engine = create_database_engine(validate_demo_database_url(DEMO_DATABASE_URL))

    @event.listens_for(engine, "checkout")
    def verify_database(dbapi_connection, _connection_record, _connection_proxy) -> None:
        with dbapi_connection.cursor() as cursor:
            cursor.execute("SELECT current_database()")
            row = cursor.fetchone()
        if row is None or row[0] != DEMO_DATABASE_NAME:
            raise DemoRealError("SQLAlchemy checked out a connection to the wrong database")

    with engine.connect() as connection:
        if connection.execute(text("SELECT current_database()")).scalar_one() != DEMO_DATABASE_NAME:
            raise DemoRealError("SQLAlchemy connected to the wrong demo database")
    return engine


def _initialize_demo(source: ObservedDatasetManifest) -> InitializedDemo:
    """Create one isolated registration and atomically import the fixed source."""

    _progress("[demo-real] Recriando somente o banco isolado e aplicando migrações...")
    _recreate_demo_database()
    _run_migrations()
    engine: Engine | None = None
    try:
        engine = _create_verified_demo_engine()
        session_factory = create_session_factory(engine)
        with session_factory() as session:
            registration = CreateFleetUseCase(PostgresInspectionRepository(session)).execute(
                CreateFleet(
                    name="Demonstração real Fendt 314",
                    tractors=(
                        CreateTractor(
                            external_id="FENDT-314-DEMO-REAL",
                            display_name="Fendt 314 — validação observada",
                        ),
                    ),
                )
            )
        if len(registration.tractors) != 1:
            raise DemoRealError("demo fleet registration did not create exactly one tractor")
        tractor_id = registration.tractors[0].id

        _progress("[demo-real] Importando o recorte observado de validação...")
        with session_factory() as session:
            imported = ImportTelemetryUseCase(PostgresTelemetryRepository(session)).execute(
                source=source.source_path,
                tractor_id=tractor_id,
                dataset_split="validation",
            )
        if imported.duplicate:
            raise DemoRealError("clean demo database unexpectedly returned a duplicate import")
        telemetry_import = imported.telemetry_import
        _verify_import_identity(telemetry_import, source)
        _progress(
            "[demo-real] Importação observada concluída: "
            f"{telemetry_import.sample_count} amostras em {telemetry_import.mission_count} missões."
        )
        return InitializedDemo(
            engine=engine,
            fleet_id=registration.fleet.id,
            tractor_id=tractor_id,
            telemetry_import=telemetry_import,
            model_version=EXPECTED_MODEL_VERSION,
        )
    except BaseException:
        if engine is not None:
            engine.dispose()
        raise


def _verify_import_identity(
    telemetry_import: TelemetryImport,
    source: ObservedDatasetManifest,
) -> None:
    expected = (
        telemetry_import.dataset_split == source.dataset_split
        and telemetry_import.source_format == "canonical_csv_gz"
        and telemetry_import.source_file_name == source.source_path.name
        and telemetry_import.source_member is None
        and telemetry_import.source_size_bytes == source.size_bytes
        and telemetry_import.source_sha256 == source.byte_sha256
        and telemetry_import.semantic_sha256 == source.semantic_sha256
        and telemetry_import.sample_count == source.sample_count
        and telemetry_import.mission_count == source.mission_count
        and telemetry_import.started_at_utc.isoformat() == source.started_at_utc
        and telemetry_import.ended_at_utc.isoformat() == source.ended_at_utc
    )
    if not expected:
        raise DemoRealError("persisted telemetry import differs from the bundled source manifest")


def _serve_and_replay(
    demo: InitializedDemo,
    source: ObservedDatasetManifest,
    *,
    accepted_window_delay_ms: float,
    no_browser: bool,
    exit_after_replay: bool,
) -> int:
    """Serve injected progress and replay in the main thread through real loopback HTTP."""

    tracker = InMemoryReplayProgress(demo, source)
    app = create_app(
        settings=Settings(database_url=DEMO_DATABASE_URL, model_dir=MODEL_DIR),
        engine=demo.engine,
        replay_progress=tracker,
    )
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=8010, log_level="warning")
    )
    server_thread = threading.Thread(
        target=server.run,
        name="demo-real-uvicorn",
        daemon=True,
    )
    vite: subprocess.Popen[bytes] | None = None
    replay_started = False
    try:
        DEMO_DIRECTORY.mkdir(parents=True, exist_ok=True)
        server_thread.start()
        vite = _start_vite()
        _wait_until_ready(f"{API_BASE_URL}/health/ready", server_thread, vite)
        _wait_until_ready(FRONTEND_BASE_URL, server_thread, vite)
        _progress("[demo-real] API e frontend responderam aos checks de readiness.")
        print(f"Demonstração real: {FRONTEND_BASE_URL}/")
        if not no_browser:
            try:
                webbrowser.open(f"{FRONTEND_BASE_URL}/")
            except OSError:
                pass

        tracker.start()
        replay_started = True
        replay = _run_live_replay(demo, accepted_window_delay_ms, tracker)
        _verify_fresh_replay(demo, source, replay)
        tracker.complete(replay)
        _progress(
            "[demo-real] Replay vivo concluído: "
            f"{replay.created_windows} janelas novas e {replay.alert_windows} alertas."
        )
        if exit_after_replay:
            return 0
        print("Pressione Ctrl-C para encerrar API e frontend; PostgreSQL e o banco demo permanecem.")
        _wait_for_interrupt(server_thread, vite)
        return 0
    except KeyboardInterrupt:
        return 0
    except (
        DemoRealError,
        ConflictError,
        ModelUnavailableError,
        TelemetryFileError,
        WindowIngestHttpError,
        WindowIngestProtocolError,
        WindowIngestTransportError,
        WindowPayloadMappingError,
        SQLAlchemyError,
        OSError,
        RuntimeError,
        ValueError,
    ) as error:
        if replay_started:
            tracker.fail()
        _progress("[demo-real] Replay falhou com DEMO_REPLAY_FAILED.")
        if not exit_after_replay and vite is not None and vite.poll() is None:
            print("A interface permanece disponível para mostrar a falha. Pressione Ctrl-C para encerrar.")
            try:
                _wait_for_interrupt(server_thread, vite)
            except (DemoRealError, KeyboardInterrupt):
                pass
        print(f"demo-real: {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    finally:
        _stop_runtime(server, server_thread, vite)
        demo.engine.dispose()


def _start_vite() -> subprocess.Popen[bytes]:
    environment = os.environ.copy()
    environment["VITE_API_PROXY_TARGET"] = API_BASE_URL
    with FRONTEND_LOG_PATH.open("ab") as frontend_log:
        return subprocess.Popen(
            [str(VITE_EXECUTABLE), "--host", "127.0.0.1", "--port", "5174", "--strictPort"],
            cwd=REPOSITORY_ROOT / "frontend",
            env=environment,
            stdout=frontend_log,
            stderr=subprocess.STDOUT,
        )


def _run_live_replay(
    demo: InitializedDemo,
    accepted_window_delay_ms: float,
    tracker: InMemoryReplayProgress,
) -> ReplayRunSummary:
    """Replay every persisted input sample once, sequentially, through Uvicorn HTTP."""

    session_factory = create_session_factory(demo.engine)
    REPLAY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with (
        session_factory() as session,
        REPLAY_PATH.open("w", encoding="utf-8") as output,
        httpx.Client(
            base_url=API_BASE_URL,
            timeout=httpx.Timeout(10.0),
            trust_env=False,
        ) as client,
    ):
        replay_source = PostgresTelemetryReplay(session, demo.telemetry_import.id)
        preflight = replay_source.preflight()
        if preflight.sample_count != demo.telemetry_import.sample_count:
            raise DemoRealError("PostgreSQL replay source does not contain every imported sample")
        provenance = ObservedReplayProvenance(
            dataset_split=preflight.telemetry_import.dataset_split,
            source_reference=replay_source_reference(preflight.telemetry_import),
            telemetry_import_id=preflight.telemetry_import.id,
        )
        return run_replay(
            replay_source.iter_samples(),
            CausalWindowAggregator(),
            HttpWindowIngestClient(client),
            provenance,
            tractor_id=demo.tractor_id,
            mission_filter=None,
            max_windows=None,
            playback_delay_ms=0.0,
            accepted_window_delay_ms=accepted_window_delay_ms,
            on_progress=tracker.observe,
            output=output,
        )


def _verify_fresh_replay(
    demo: InitializedDemo,
    source: ObservedDatasetManifest,
    replay: ReplayRunSummary,
) -> None:
    """Verify structural live inference without comparing against stored model outputs."""

    expected_summary = (
        replay.status == "complete"
        and replay.tractor_id == demo.tractor_id
        and replay.dataset_split == "validation"
        and replay.mission_filter is None
        and replay.samples_replayed == source.sample_count
        and replay.ready_windows > 0
        and replay.created_windows == replay.ready_windows
        and replay.duplicate_windows == 0
        and replay.failures == 0
        and replay.stopped_at_limit is False
    )
    if not expected_summary:
        raise DemoRealError("live replay did not consume the complete source as fresh inference")

    session_factory = create_session_factory(demo.engine)
    with session_factory() as session:
        statement = select(ScoredWindowRecord).where(
            ScoredWindowRecord.tractor_id == UUID(demo.tractor_id)
        )
        persisted_count = int(
            session.scalar(select(func.count()).select_from(statement.subquery())) or 0
        )
        model_versions = set(
            session.scalars(
                select(ScoredWindowRecord.model_version).where(
                    ScoredWindowRecord.tractor_id == UUID(demo.tractor_id)
                )
            )
        )
        import_ids = set(
            session.scalars(
                select(ScoredWindowRecord.telemetry_import_id).where(
                    ScoredWindowRecord.tractor_id == UUID(demo.tractor_id)
                )
            )
        )
    if persisted_count != replay.created_windows:
        raise DemoRealError("persisted live inference count differs from the replay result")
    if model_versions != {demo.model_version}:
        raise DemoRealError("persisted live inference model version differs from the frozen bundle")
    if import_ids != {UUID(demo.telemetry_import.id)}:
        raise DemoRealError("persisted live inference lineage differs from the imported source")
    with httpx.Client(base_url=API_BASE_URL, timeout=10.0, trust_env=False) as client:
        response = client.get(f"/v1/tractors/{demo.tractor_id}/overview")
    if response.status_code != 200:
        raise DemoRealError("live tractor overview did not aggregate the fresh replay")
    try:
        overview = response.json()
    except json.JSONDecodeError as error:
        raise DemoRealError("live tractor overview returned invalid JSON") from error
    if (
        not isinstance(overview, dict)
        or overview.get("evidence_role") != "operational_output_only"
        or not isinstance(overview.get("scores"), dict)
    ):
        raise DemoRealError("live tractor overview returned an invalid evidence contract")


def _wait_until_ready(
    url: str,
    server_thread: threading.Thread,
    vite: subprocess.Popen[bytes],
    *,
    timeout_seconds: float = 30.0,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not server_thread.is_alive():
            raise DemoRealError("demo API stopped before readiness")
        if vite.poll() is not None:
            raise DemoRealError(f"demo frontend stopped before readiness; inspect {FRONTEND_LOG_PATH}")
        try:
            with urlopen(url, timeout=1.0) as response:
                if response.status == 200:
                    return
        except (URLError, OSError):
            pass
        time.sleep(0.2)
    raise DemoRealError(f"timed out waiting for local readiness at {url}")


def _wait_for_interrupt(
    server_thread: threading.Thread,
    vite: subprocess.Popen[bytes],
) -> None:
    while True:
        if not server_thread.is_alive():
            raise DemoRealError("demo API stopped")
        if vite.poll() is not None:
            raise DemoRealError(f"demo frontend stopped; inspect {FRONTEND_LOG_PATH}")
        time.sleep(0.5)


def _stop_runtime(
    server: uvicorn.Server,
    server_thread: threading.Thread,
    vite: subprocess.Popen[bytes] | None,
) -> None:
    if vite is not None and vite.poll() is None:
        vite.terminate()
        try:
            vite.wait(timeout=5)
        except subprocess.TimeoutExpired:
            vite.kill()
            vite.wait(timeout=5)
    server.should_exit = True
    server_thread.join(timeout=5)
    if server_thread.is_alive():
        server.force_exit = True
        server_thread.join(timeout=5)


def _safe_relative_source_path(manifest_path: Path, value: str) -> Path:
    relative = Path(value)
    if relative.is_absolute() or not value or ".." in relative.parts:
        raise DemoRealError("observed dataset file_name must be a safe relative path")
    directory = manifest_path.parent.resolve()
    candidate = (directory / relative).resolve()
    try:
        candidate.relative_to(directory)
    except ValueError as error:
        raise DemoRealError("observed dataset file_name escapes its manifest directory") from error
    return candidate


def _load_json_object(path: Path, label: str) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DemoRealError(f"{label} is unavailable or invalid: {path}") from error
    if not isinstance(value, dict):
        raise DemoRealError(f"{label} must be a JSON object")
    return value


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise DemoRealError(f"{field} must be non-empty text")
    return value


def _sha256_text(value: object, field: str) -> str:
    text_value = _text(value, field)
    if len(text_value) != 64 or any(character not in "0123456789abcdef" for character in text_value):
        raise DemoRealError(f"{field} must be a lowercase SHA-256 hex digest")
    return text_value


def _positive_integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise DemoRealError(f"{field} must be a positive integer")
    return value


def _utc_text(value: object, field: str) -> str:
    raw = _text(value, field)
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as error:
        raise DemoRealError(f"{field} must be an ISO timestamp") from error
    if parsed.tzinfo is None:
        raise DemoRealError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat()


def _non_negative_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("value must be a non-negative number") from error
    if not math.isfinite(parsed) or parsed < 0:
        raise argparse.ArgumentTypeError("value must be a non-negative number")
    return parsed


def _progress(message: str) -> None:
    print(message, flush=True)


def main() -> int:
    args = _parser().parse_args()
    try:
        validate_demo_database_url(DEMO_DATABASE_URL)
        source = _preflight()
        demo = _initialize_demo(source)
        return _serve_and_replay(
            demo,
            source,
            accepted_window_delay_ms=args.window_delay_ms,
            no_browser=args.no_browser,
            exit_after_replay=args.exit_after_replay,
        )
    except DemoRealError as error:
        print(f"demo-real: {error}", file=sys.stderr)
        return 1
    except (SQLAlchemyError, psycopg.Error):
        print("demo-real: isolated PostgreSQL operation failed", file=sys.stderr)
        return 1
    except (TelemetryFileError, OSError, RuntimeError, ValueError) as error:
        print(f"demo-real: {type(error).__name__}: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
