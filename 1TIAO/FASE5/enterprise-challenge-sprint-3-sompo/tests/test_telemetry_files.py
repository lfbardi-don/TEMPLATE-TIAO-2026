from __future__ import annotations

import csv
from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path
import zipfile

import pytest

from tractor_usage.infrastructure.telemetry_files import (
    ORIGINAL_SIGNAL_COLUMNS,
    TelemetryFileError,
    TelemetryFileSource,
)
from tractor_usage.application.contracts import Tractor
from tractor_usage.application.telemetry import ImportTelemetryUseCase
from tractor_usage.streaming.replay import RAW_SIGNAL_FIELDS, REPLAY_COLUMNS


def _canonical_row(*, mission: int, position: str, source_row: int) -> dict[str, str]:
    return {
        "mission_index": str(mission),
        "position_seconds": position,
        "source_row": str(source_row),
        **{field: "1.5" for field in RAW_SIGNAL_FIELDS},
    }


def test_canonical_source_requires_exact_header_and_streams_only_frozen_split(tmp_path: Path) -> None:
    source = tmp_path / "observed.csv"
    with source.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=REPLAY_COLUMNS)
        writer.writeheader()
        writer.writerow(_canonical_row(mission=4, position="204.3", source_row=0))
        writer.writerow(_canonical_row(mission=4, position="205.3", source_row=1))
    reader = TelemetryFileSource(source, "train")

    scan = reader.scan()
    samples = tuple(reader.iter_selected_samples())

    assert scan.source_format == "canonical_csv"
    assert scan.sample_count == 2
    assert scan.missions[0].origin_position_deciseconds == 2043
    assert [sample.position_deciseconds for sample in samples] == [2043, 2053]
    assert samples[0].values["engine_rpm"] == 1.5


def test_original_zip_maps_exact_headers_and_creates_missions_only_for_gap_over_one_second(tmp_path: Path) -> None:
    member = tmp_path / "Fendt 314.csv"
    headers = ["Time_(s)", "index_[-]", "Tractor_Model_[-]", *ORIGINAL_SIGNAL_COLUMNS]
    rows = [
        ["204,3", "10", "Fendt 314", *("1,5" for _ in ORIGINAL_SIGNAL_COLUMNS)],
        ["205,3", "11", "Fendt 314", *("1,5" for _ in ORIGINAL_SIGNAL_COLUMNS)],
        ["206,4", "12", "Fendt 314", *("1,5" for _ in ORIGINAL_SIGNAL_COLUMNS)],
        ["207,4", "13", "Fendt 314", *("1,5" for _ in ORIGINAL_SIGNAL_COLUMNS)],
    ]
    with member.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(headers)
        writer.writerows(rows)
    source = tmp_path / "Fendt 314.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.write(member, "folder/Fendt 314.csv")

    reader = TelemetryFileSource(source, "train")
    scan = reader.scan()
    samples = tuple(reader.iter_selected_samples())

    assert scan.source_member == "folder/Fendt 314.csv"
    assert [sample.mission_index for sample in samples] == [0, 0, 1, 1]
    assert [sample.mission_origin_position_deciseconds for sample in samples] == [2043, 2043, 2064, 2064]
    assert samples[0].values["wheel_vehicle_speed_kph"] == 1.5


def test_original_zip_parses_the_real_timedelta_text_export(tmp_path: Path) -> None:
    member = tmp_path / "Fendt 314.csv"
    headers = ["Time_(s)", "index_[-]", "Tractor_Model_[-]", *ORIGINAL_SIGNAL_COLUMNS]
    rows = [
        ["0 days 00:03:24.300000", "10", "Fendt 314", *("1.5" for _ in ORIGINAL_SIGNAL_COLUMNS)],
        ["0 days 00:03:25.300000", "11", "Fendt 314", *("1.5" for _ in ORIGINAL_SIGNAL_COLUMNS)],
    ]
    with member.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)
    source = tmp_path / "Fendt 314.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.write(member, "Fendt 314 - Kopie/Fendt 314.csv")

    reader = TelemetryFileSource(source, "train")
    reader.scan()
    assert [sample.position_deciseconds for sample in reader.iter_selected_samples()] == [2043, 2053]


def test_canonical_rejects_positions_not_representable_in_deciseconds(tmp_path: Path) -> None:
    source = tmp_path / "observed.csv"
    with source.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=REPLAY_COLUMNS)
        writer.writeheader()
        writer.writerow(_canonical_row(mission=0, position="204.31", source_row=0))

    with pytest.raises(TelemetryFileError, match="deciseconds"):
        TelemetryFileSource(source, "train").scan()


def test_canonical_rejects_decreasing_mission_ids_between_blocks(tmp_path: Path) -> None:
    source = tmp_path / "observed.csv"
    with source.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=REPLAY_COLUMNS)
        writer.writeheader()
        writer.writerow(_canonical_row(mission=9, position="204.3", source_row=0))
        writer.writerow(_canonical_row(mission=2, position="205.3", source_row=1))

    with pytest.raises(TelemetryFileError, match="mission_index must increase"):
        TelemetryFileSource(source, "train").scan()


def test_semantic_digest_normalizes_signed_zero(tmp_path: Path) -> None:
    positive = tmp_path / "positive.csv"
    negative = tmp_path / "negative.csv"
    for path, zero in ((positive, "0"), (negative, "-0.0")):
        row = _canonical_row(mission=4, position="204.3", source_row=0)
        row["engine_rpm"] = zero
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=REPLAY_COLUMNS)
            writer.writeheader()
            writer.writerow(row)

    positive_reader = TelemetryFileSource(positive, "train")
    negative_reader = TelemetryFileSource(negative, "train")
    assert positive_reader.scan().semantic_sha256 == negative_reader.scan().semantic_sha256
    assert next(negative_reader.iter_selected_samples()).values["engine_rpm"] == 0.0


class _ImportRepository:
    def __init__(self) -> None:
        self.imports = []
        self.samples = []

    def transaction(self):
        return nullcontext()

    def get_tractor(self, tractor_id: str, *, for_update: bool = False):
        return Tractor(tractor_id, "fleet", "F314", None, "Fendt 314", datetime.now(timezone.utc))

    def find_import_by_source(self, tractor_id, dataset_split, source_sha256, transform_version):
        return next((item for item in self.imports if item.source_sha256 == source_sha256), None)

    def find_import_by_semantic_digest(self, semantic_sha256):
        return next((item for item in self.imports if item.semantic_sha256 == semantic_sha256), None)

    def create_import(self, telemetry_import, missions):
        self.imports.append(telemetry_import)
        return telemetry_import

    def insert_samples(self, import_id, samples):
        self.samples.extend(samples)


def test_import_use_case_is_idempotent_by_source_without_reinserting_samples(tmp_path: Path) -> None:
    source = tmp_path / "observed.csv"
    with source.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=REPLAY_COLUMNS)
        writer.writeheader()
        writer.writerow(_canonical_row(mission=4, position="204.3", source_row=0))
        writer.writerow(_canonical_row(mission=4, position="205.3", source_row=1))
    repository = _ImportRepository()
    use_case = ImportTelemetryUseCase(repository)

    first = use_case.execute(source=source, tractor_id="tractor-1", dataset_split="train", batch_size=1)
    repeated = use_case.execute(source=source, tractor_id="tractor-1", dataset_split="train", batch_size=1)

    assert first.duplicate is False
    assert repeated.duplicate is True
    assert len(repository.imports) == 1
    assert len(repository.samples) == 2
