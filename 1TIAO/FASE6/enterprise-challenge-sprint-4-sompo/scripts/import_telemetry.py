"""Atomically import an approved Fendt 314 telemetry CSV or ZIP into PostgreSQL."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError

from tractor_usage.application.contracts import ConflictError, NotFoundError
from tractor_usage.application.telemetry import ImportTelemetryUseCase
from tractor_usage.infrastructure.database import Settings, create_database_engine, create_session_factory
from tractor_usage.infrastructure.telemetry_files import TelemetryFileError
from tractor_usage.infrastructure.telemetry_repository import PostgresTelemetryRepository


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=_source_path)
    parser.add_argument("--tractor-id", required=True, type=_uuid)
    parser.add_argument("--dataset-split", required=True, choices=("train", "validation"))
    parser.add_argument("--batch-size", default=5_000, type=_positive_int)
    parser.add_argument("--database-url")
    return parser


def _source_path(value: str) -> Path:
    path = Path(value)
    if not path.is_file():
        raise argparse.ArgumentTypeError("source must be an existing local file")
    return path


def _uuid(value: str) -> str:
    try:
        return str(UUID(value))
    except ValueError as error:
        raise argparse.ArgumentTypeError("tractor-id must be a UUID") from error


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("batch-size must be a positive integer") from error
    if parsed <= 0:
        raise argparse.ArgumentTypeError("batch-size must be a positive integer")
    return parsed


def _event(result) -> dict[str, object]:
    telemetry_import = result.telemetry_import
    return {
        "event": "TELEMETRY_IMPORT_COMPLETED",
        "duplicate": result.duplicate,
        "import_id": telemetry_import.id,
        "tractor_id": telemetry_import.tractor_id,
        "dataset_split": telemetry_import.dataset_split,
        "source_format": telemetry_import.source_format,
        "source_sha256": telemetry_import.source_sha256,
        "semantic_sha256": telemetry_import.semantic_sha256,
        "mission_count": telemetry_import.mission_count,
        "sample_count": telemetry_import.sample_count,
        "started_at_utc": telemetry_import.started_at_utc.isoformat(),
        "ended_at_utc": telemetry_import.ended_at_utc.isoformat(),
    }


def main() -> None:
    args = _parser().parse_args()
    engine = create_database_engine(args.database_url or Settings.from_environment().database_url)
    try:
        with create_session_factory(engine)() as session:
            result = ImportTelemetryUseCase(PostgresTelemetryRepository(session)).execute(
                source=args.source,
                tractor_id=args.tractor_id,
                dataset_split=args.dataset_split,
                batch_size=args.batch_size,
            )
        print(json.dumps(_event(result), sort_keys=True, allow_nan=False))
    except ConflictError as error:
        print(json.dumps({"event": "ERROR", "detail": str(error)}), file=sys.stderr)
        raise SystemExit(4) from error
    except (TelemetryFileError, ValueError, NotFoundError) as error:
        print(json.dumps({"event": "ERROR", "detail": str(error)}), file=sys.stderr)
        raise SystemExit(2) from error
    except SQLAlchemyError as error:
        print(json.dumps({"event": "ERROR", "detail": "database unavailable"}), file=sys.stderr)
        raise SystemExit(3) from error
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
