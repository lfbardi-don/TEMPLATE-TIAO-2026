from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import pytest

from scripts import demo_real
from scripts.demo_real import (
    DATASET_MANIFEST_PATH,
    DEMO_DATABASE_URL,
    EXPECTED_DATASET_SHA256,
    EXPECTED_MISSION_COUNT,
    EXPECTED_SAMPLE_COUNT,
    EXPECTED_SEMANTIC_SHA256,
    EXPECTED_SOURCE_DOI,
    EXPECTED_SOURCE_LICENSE,
    DemoRealError,
    InMemoryReplayProgress,
    InitializedDemo,
    ObservedDatasetManifest,
    _configured_demo_database_url,
    _configured_postgres_port,
    _create_demo_accounts,
    _expected_postgres_data_dir,
    _parser,
    _recreate_demo_database,
    _require_expected_postgres_data_dir,
    load_observed_dataset_manifest,
    validate_demo_database_url,
)
from scripts.run_api_replay import ReplayRunProgress, ReplayRunSummary
from tractor_usage.infrastructure.http_window_ingest import IngestReceipt


TRACTOR_ID = "8e4aac40-93c2-4b79-88c5-d75b257e7685"
IMPORT_ID = "9313f9b2-7042-4c60-8f20-3cee669f578d"


def _source() -> ObservedDatasetManifest:
    return ObservedDatasetManifest(
        source_path=Path("data/fendt314-validation/fendt314-validation-observed.csv.gz"),
        dataset_split="validation",
        source_doi=EXPECTED_SOURCE_DOI,
        source_license=EXPECTED_SOURCE_LICENSE,
        size_bytes=6_627_620,
        byte_sha256=EXPECTED_DATASET_SHA256,
        semantic_sha256=EXPECTED_SEMANTIC_SHA256,
        sample_count=152_561,
        mission_count=105,
        started_at_utc="2024-09-07T10:18:16.200000+00:00",
        ended_at_utc="2024-10-19T18:59:46.700000+00:00",
    )


def _demo() -> InitializedDemo:
    return InitializedDemo(
        engine=SimpleNamespace(),
        fleet_id="fleet-id",
        tractor_id=TRACTOR_ID,
        telemetry_import=SimpleNamespace(id=IMPORT_ID, dataset_split="validation"),
        model_version="fendt314-hybrid-v2.0.1",
    )


def _summary(index: int, *, status: str = "partial") -> ReplayRunSummary:
    return ReplayRunSummary(
        status=status,
        tractor_id=TRACTOR_ID,
        dataset_split="validation",
        source_reference="postgresql:telemetry-import:test",
        mission_filter=None,
        samples_replayed=(index + 1) * 60,
        ready_windows=index + 1,
        created_windows=index + 1,
        duplicate_windows=0,
        alert_windows=index,
        no_data_windows=0,
        failures=0,
        stopped_at_limit=False,
    )


def _receipt(index: int) -> IngestReceipt:
    return IngestReceipt(
        http_status=201,
        duplicate=False,
        window_id=f"window-{index}",
        tractor_id=TRACTOR_ID,
        mission_index=271,
        window_index=index,
        idempotency_key="a" * 64,
        model_version="fendt314-hybrid-v2.0.1",
        hybrid_alert=bool(index % 2),
    )


def test_database_url_guard_accepts_only_the_isolated_local_psycopg_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DEMO_POSTGRES_PORT", raising=False)
    assert validate_demo_database_url(DEMO_DATABASE_URL) == DEMO_DATABASE_URL

    rejected = (
        "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/tractor_usage",
        "postgresql+psycopg://postgres:postgres@10.0.0.2:5432/tractor_usage_demo_real",
        "postgresql+psycopg://app:postgres@127.0.0.1:5432/tractor_usage_demo_real",
        "postgresql+psycopg://postgres:postgres@127.0.0.1:5433/tractor_usage_demo_real",
        "postgresql://postgres:postgres@127.0.0.1:5432/tractor_usage_demo_real",
    )
    for value in rejected:
        with pytest.raises(DemoRealError):
            validate_demo_database_url(value)


@pytest.mark.parametrize("value", ["", "zero", "0", "65536", "1.5", "-1"])
def test_alternate_demo_port_must_be_valid(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("DEMO_POSTGRES_PORT", value)
    with pytest.raises(DemoRealError, match="DEMO_POSTGRES_PORT"):
        _configured_postgres_port()


def test_alternate_demo_port_requires_a_matching_temporary_cluster(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEMO_POSTGRES_PORT", "55432")
    url = _configured_demo_database_url()
    assert ":55432/tractor_usage_demo_real" in url
    assert validate_demo_database_url(url) == url
    with pytest.raises(DemoRealError):
        validate_demo_database_url(DEMO_DATABASE_URL)
    with pytest.raises(DemoRealError, match="DEMO_POSTGRES_DATA_DIR"):
        _expected_postgres_data_dir()

    monkeypatch.setenv("DEMO_POSTGRES_DATA_DIR", str(Path.cwd()))
    with pytest.raises(DemoRealError, match="under /tmp"):
        _expected_postgres_data_dir()

    with TemporaryDirectory(dir="/tmp") as directory:
        expected = Path(directory).resolve()
        monkeypatch.setenv("DEMO_POSTGRES_DATA_DIR", directory)
        assert _expected_postgres_data_dir() == expected

        class Cursor:
            def execute(self, statement: str) -> None:
                assert statement == "SHOW data_directory"

            def fetchone(self) -> tuple[str]:
                return (directory,)

        _require_expected_postgres_data_dir(Cursor())  # type: ignore[arg-type]


def test_alternate_demo_cluster_mismatch_stops_before_database_recreation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEMO_POSTGRES_PORT", "55432")
    with TemporaryDirectory(dir="/tmp") as directory:
        monkeypatch.setenv("DEMO_POSTGRES_DATA_DIR", directory)
        statements: list[str] = []

        class Cursor:
            def __enter__(self):
                return self

            def __exit__(self, *_: object) -> bool:
                return False

            def execute(self, statement: str, params: object = None) -> None:
                statements.append(statement)

            def fetchone(self) -> tuple[str]:
                if statements[-1] == "SELECT current_database()":
                    return ("postgres",)
                return (str(Path.cwd()),)

        class Connection:
            def __enter__(self):
                return self

            def __exit__(self, *_: object) -> bool:
                return False

            def cursor(self) -> Cursor:
                return Cursor()

        monkeypatch.setattr(demo_real.psycopg, "connect", lambda **_: Connection())

        with pytest.raises(DemoRealError, match="data directory differs"):
            _recreate_demo_database()
        assert statements == ["SELECT current_database()", "SHOW data_directory"]


def test_bundled_manifest_exposes_only_the_approved_observed_source_identity() -> None:
    source = load_observed_dataset_manifest()
    raw = json.loads(DATASET_MANIFEST_PATH.read_text(encoding="utf-8"))

    assert source.source_path.name == "fendt314-validation-observed.csv.gz"
    assert source.source_doi == EXPECTED_SOURCE_DOI
    assert source.source_license == EXPECTED_SOURCE_LICENSE
    assert source.semantic_sha256 == EXPECTED_SEMANTIC_SHA256
    assert source.sample_count == EXPECTED_SAMPLE_COUNT
    assert source.mission_count == EXPECTED_MISSION_COUNT
    assert not {"alerts", "episodes", "scores", "horizons"} & set(raw)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("file_name", "../outside.csv.gz", "safe relative"),
        ("source_license", "CC-BY-3.0", "identity"),
        ("sample_count", 1, "identity"),
        ("semantic_sha256", "a" * 64, "identity"),
    ],
)
def test_manifest_rejects_source_identity_or_path_drift(
    tmp_path: Path,
    field: str,
    value: object,
    message: str,
) -> None:
    raw = json.loads(DATASET_MANIFEST_PATH.read_text(encoding="utf-8"))
    raw[field] = value
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(DemoRealError, match=message):
        load_observed_dataset_manifest(path)


def test_demo_cli_has_no_arbitrary_source_parameter() -> None:
    parsed = _parser().parse_args(["--no-browser", "--exit-after-replay"])

    assert parsed.window_delay_ms == 20.0
    assert parsed.no_browser is True
    assert parsed.exit_after_replay is True
    with pytest.raises(SystemExit):
        _parser().parse_args(["--source", "/tmp/other.csv.gz"])
    with pytest.raises(SystemExit):
        _parser().parse_args(["--window-delay-ms", "-1"])


def test_demo_creates_fresh_accounts_with_scoped_manager(monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[dict[str, object]] = []

    class Session:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    class Repository:
        def __init__(self, _: Session) -> None:
            pass

        def create_user(self, **kwargs: object) -> None:
            created.append(kwargs)

    monkeypatch.setattr(demo_real, "create_session_factory", lambda _: lambda: Session())
    monkeypatch.setattr(demo_real, "AuthRepository", Repository)

    accounts = _create_demo_accounts(_demo())

    assert [entry["role"] for entry in created] == ["ADMIN", "INSURER", "INSPECTOR", "FLEET_MANAGER"]
    assert [entry["fleet_id"] for entry in created] == [None, None, None, "fleet-id"]
    assert [account[1] for account in accounts] == [entry["worker_id"] for entry in created]
    assert [account[1] for account in accounts] == ["1000", "1001", "1002", "1003"]
    assert all(len(account[2]) >= 12 for account in accounts)
    assert len({account[2] for account in accounts}) == 4


def test_tracker_is_lock_safe_monotonic_and_keeps_only_eight_committed_decisions() -> None:
    tracker = InMemoryReplayProgress(_demo(), _source())

    assert tracker.snapshot().status == "waiting"
    tracker.start()
    for index in range(10):
        tracker.observe(ReplayRunProgress(summary=_summary(index), receipt=_receipt(index)))

    running = tracker.snapshot()
    assert running.status == "running"
    assert running.created_windows == 10
    assert [item.window_index for item in running.recent_inferences] == list(range(2, 10))

    tracker.complete(_summary(9, status="complete"))
    completed = tracker.snapshot()
    assert completed.status == "complete"
    assert completed.error_code is None
    with pytest.raises(DemoRealError, match="completed"):
        tracker.fail()


def test_tracker_rejects_counter_regression_and_exposes_only_a_safe_failure_code() -> None:
    tracker = InMemoryReplayProgress(_demo(), _source())
    tracker.start()
    tracker.observe(ReplayRunProgress(summary=_summary(2), receipt=_receipt(2)))

    with pytest.raises(DemoRealError, match="monotonic"):
        tracker.observe(ReplayRunProgress(summary=_summary(1), receipt=_receipt(1)))

    tracker.fail()
    failed = tracker.snapshot()
    assert failed.status == "failed"
    assert failed.error_code == "DEMO_REPLAY_FAILED"
    assert failed.failures == 1
