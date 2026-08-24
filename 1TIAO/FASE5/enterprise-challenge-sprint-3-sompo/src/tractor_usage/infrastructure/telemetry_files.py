"""Streaming readers for the two approved observed-telemetry source formats.

The readers deliberately stop before feature engineering.  They are used twice by
the importer: once to validate and calculate the semantic digest and once inside
the database transaction to stream the same selected rows into PostgreSQL.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import gzip
from hashlib import sha256
import json
import math
from pathlib import Path
from typing import Iterator, TextIO
import zipfile

from tractor_usage.application.contracts import PersistedTelemetrySample, TelemetrySourceFormat
from tractor_usage.streaming.replay import FENDT_314_EPOCH_UTC, RAW_SIGNAL_FIELDS, REPLAY_COLUMNS


EPOCH_UTC = FENDT_314_EPOCH_UTC.to_pydatetime().astimezone(timezone.utc)
SCHEMA_VERSION = "fendt314-telemetry-v1"
CANONICAL_TRANSFORM = "canonical-pass-through-v1"
ORIGINAL_TRANSFORM = "fendt314-original-to-1hz-v1"
ORIGINAL_MEMBER_BASENAME = "Fendt 314.csv"

ORIGINAL_SIGNAL_COLUMNS = {
    "EngSpeed_(RPM)": "engine_rpm",
    "ActualEngPercentTorque_(%)": "actual_engine_torque_pct",
    "EngPercentLoadAtCurrentSpeed_(%)": "engine_load_pct",
    "AccelPedalPos1_(%)": "accelerator_pct",
    "EngCoolantTemp_(°C)": "coolant_temp_c",
    "FrontAxleSpeed_(km/h)": "front_axle_speed_kph",
    "SpeedOverGround_(m/s)": "speed_over_ground_mps",
    "GroundBasedImplementSpeed_[mm/s]": "ground_implement_speed_mmps",
    "WheelBasedVehicleSpeed _(km/h)": "wheel_vehicle_speed_kph",
    "RearPTOOutputShaftSpeed_(RPM)": "rear_pto_rpm",
    "RearHitchPosition_[-]": "rear_hitch_position",
    "RearHitchInWorkIndication_[-]": "rear_hitch_in_work",
    "RearNominalLowerLinkForce_(%)": "rear_link_force_pct",
    "RearDraft_(N)": "rear_draft_n",
    "GroundBasedMachineSpeed_(m/s)": "ground_machine_speed_mps",
    "MachineSelectedSpeed_(m/s)": "machine_selected_speed_mps",
    "WheelBasedMachineSpeed_(m/s)": "wheel_machine_speed_mps",
}


class TelemetryFileError(ValueError):
    """The supplied local source does not meet the frozen telemetry contract."""


@dataclass(frozen=True)
class TelemetryMissionDraft:
    mission_index: int
    origin_position_deciseconds: int
    first_position_deciseconds: int
    last_position_deciseconds: int
    first_source_row: int
    last_source_row: int
    started_at_utc: datetime
    ended_at_utc: datetime
    sample_count: int


@dataclass(frozen=True)
class TelemetrySourceScan:
    source_format: TelemetrySourceFormat
    source_member: str | None
    transform_version: str
    semantic_sha256: str
    sample_count: int
    started_at_utc: datetime
    ended_at_utc: datetime
    missions: tuple[TelemetryMissionDraft, ...]


class TelemetryFileSource:
    """Validated source plus a deterministic second-pass iterator."""

    def __init__(self, path: Path, dataset_split: str) -> None:
        if not path.is_file():
            raise TelemetryFileError("source must be an existing local file")
        if dataset_split not in ("train", "validation"):
            raise TelemetryFileError("dataset_split must be train or validation")
        self.path = path
        self.dataset_split = dataset_split
        self.source_format = _source_format(path)
        self._scan: TelemetrySourceScan | None = None
        self._source_sha256: str | None = None
        self._hashed_signature: tuple[int, int] | None = None

    @property
    def source_size_bytes(self) -> int:
        return self.path.stat().st_size

    @property
    def transform_version(self) -> str:
        if self.source_format in ("canonical_csv", "canonical_csv_gz"):
            return CANONICAL_TRANSFORM
        return ORIGINAL_TRANSFORM

    @property
    def source_sha256(self) -> str:
        if self._source_sha256 is not None:
            return self._source_sha256
        before = self.path.stat()
        digest = sha256()
        with self.path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        after = self.path.stat()
        before_signature = (before.st_size, before.st_mtime_ns)
        after_signature = (after.st_size, after.st_mtime_ns)
        if after_signature != before_signature:
            raise TelemetryFileError("source changed while its checksum was being calculated")
        self._source_sha256 = digest.hexdigest()
        self._hashed_signature = after_signature
        return self._source_sha256

    def scan(self) -> TelemetrySourceScan:
        if self._scan is None:
            samples = self._iter_selected_samples()
            digest = sha256()
            digest.update((SCHEMA_VERSION + "\n").encode("utf-8"))
            mission_stats: dict[int, _MissionStats] = {}
            count = 0
            first: datetime | None = None
            last: datetime | None = None
            for sample in samples:
                _update_semantic_digest(digest, sample)
                stat = mission_stats.get(sample.mission_index)
                if stat is None:
                    stat = _MissionStats.from_sample(sample)
                    mission_stats[sample.mission_index] = stat
                else:
                    stat.add(sample)
                count += 1
                first = sample.observed_at_utc if first is None else first
                last = sample.observed_at_utc
            if count == 0 or first is None or last is None:
                raise TelemetryFileError("source has no samples in the selected frozen split")
            source_member = _source_member(self.path, self.source_format)
            self._scan = TelemetrySourceScan(
                source_format=self.source_format,
                source_member=source_member,
                transform_version=self.transform_version,
                semantic_sha256=digest.hexdigest(),
                sample_count=count,
                started_at_utc=first,
                ended_at_utc=last,
                missions=tuple(stat.freeze() for _, stat in sorted(mission_stats.items())),
            )
        return self._scan

    def iter_selected_samples(self) -> Iterator[PersistedTelemetrySample]:
        # A caller must scan first, so metadata and persisted rows are bound to
        # one validated deterministic source interpretation.
        if self._scan is None:
            raise RuntimeError("scan must complete before telemetry samples are consumed")
        digest = sha256()
        digest.update((SCHEMA_VERSION + "\n").encode("utf-8"))
        count = 0
        for sample in self._iter_selected_samples():
            _update_semantic_digest(digest, sample)
            count += 1
            yield sample
        if count != self._scan.sample_count or digest.hexdigest() != self._scan.semantic_sha256:
            raise TelemetryFileError("source changed after telemetry validation")
        if self._hashed_signature is not None:
            current = self.path.stat()
            if (current.st_size, current.st_mtime_ns) != self._hashed_signature:
                raise TelemetryFileError("source changed after its checksum was calculated")

    def _iter_selected_samples(self) -> Iterator[PersistedTelemetrySample]:
        start, end = _split_interval(self.dataset_split)
        if self.source_format in ("canonical_csv", "canonical_csv_gz"):
            yield from _canonical_samples(self.path, start, end)
            return
        yield from _original_zip_samples(self.path, start, end)


@dataclass
class _MissionStats:
    mission_index: int
    origin_position_deciseconds: int
    first_position_deciseconds: int
    last_position_deciseconds: int
    first_source_row: int
    last_source_row: int
    started_at_utc: datetime
    ended_at_utc: datetime
    sample_count: int

    @classmethod
    def from_sample(cls, sample: PersistedTelemetrySample) -> "_MissionStats":
        return cls(
            mission_index=sample.mission_index,
            origin_position_deciseconds=sample.mission_origin_position_deciseconds,
            first_position_deciseconds=sample.position_deciseconds,
            last_position_deciseconds=sample.position_deciseconds,
            first_source_row=sample.source_row,
            last_source_row=sample.source_row,
            started_at_utc=sample.observed_at_utc,
            ended_at_utc=sample.observed_at_utc,
            sample_count=1,
        )

    def add(self, sample: PersistedTelemetrySample) -> None:
        self.last_position_deciseconds = sample.position_deciseconds
        self.last_source_row = sample.source_row
        self.ended_at_utc = sample.observed_at_utc
        self.sample_count += 1

    def freeze(self) -> TelemetryMissionDraft:
        return TelemetryMissionDraft(**self.__dict__)


def _source_format(path: Path) -> TelemetrySourceFormat:
    suffixes = tuple(s.lower() for s in path.suffixes)
    if suffixes[-1:] == (".zip",):
        return "fendt314_zip"
    if suffixes[-2:] == (".csv", ".gz"):
        return "canonical_csv_gz"
    if suffixes[-1:] == (".csv",):
        return "canonical_csv"
    raise TelemetryFileError("source must end in .csv, .csv.gz, or .zip")


def _source_member(path: Path, source_format: TelemetrySourceFormat) -> str | None:
    if source_format != "fendt314_zip":
        return None
    with zipfile.ZipFile(path) as archive:
        members = [name for name in archive.namelist() if Path(name).name == ORIGINAL_MEMBER_BASENAME]
    if len(members) != 1:
        raise TelemetryFileError("ZIP must contain exactly one Fendt 314.csv member")
    return members[0]


def _split_interval(dataset_split: str) -> tuple[datetime, datetime]:
    manifest_path = Path(__file__).resolve().parents[3] / "models" / "fendt314-hybrid-v2.0.1" / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        provenance = manifest["provenance"]
        start = _parse_utc(provenance[f"{dataset_split}_start_utc"])
        end = _parse_utc(provenance[f"{dataset_split}_end_utc"]) + timedelta(seconds=60)
    except (OSError, KeyError, TypeError, ValueError) as error:
        raise TelemetryFileError("approved manifest does not expose frozen split bounds") from error
    return start, end


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _open_text(path: Path) -> TextIO:
    if path.suffix.lower() == ".gz":
        return gzip.open(path, "rt", encoding="utf-8-sig", newline="")
    return path.open("rt", encoding="utf-8-sig", newline="")


def _csv_rows(handle: TextIO) -> Iterator[dict[str, str]]:
    header = handle.readline()
    if not header:
        raise TelemetryFileError("CSV is empty")
    delimiter = ";" if header.count(";") > header.count(",") else ","
    headers = next(csv.reader([header], delimiter=delimiter))
    reader = csv.DictReader(handle, fieldnames=headers, delimiter=delimiter)
    yield from reader


def _canonical_samples(path: Path, start: datetime, end: datetime) -> Iterator[PersistedTelemetrySample]:
    previous_position: int | None = None
    active_mission: int | None = None
    seen_missions: set[int] = set()
    origins: dict[int, int] = {}
    source_rows: set[int] = set()
    with _open_text(path) as handle:
        header = handle.readline()
        if not header:
            raise TelemetryFileError("CSV is empty")
        delimiter = ";" if header.count(";") > header.count(",") else ","
        headers = tuple(next(csv.reader([header], delimiter=delimiter)))
        if headers != REPLAY_COLUMNS:
            raise TelemetryFileError("canonical CSV header must exactly match REPLAY_COLUMNS")
        reader = csv.DictReader(handle, fieldnames=headers, delimiter=delimiter)
        for record in reader:
            mission = _non_negative_int(record["mission_index"], "mission_index")
            position = _deciseconds(record["position_seconds"], "position_seconds")
            source_row = _non_negative_int(record["source_row"], "source_row")
            if source_row in source_rows:
                raise TelemetryFileError("canonical source_row must be unique")
            source_rows.add(source_row)
            if previous_position is not None and position <= previous_position:
                raise TelemetryFileError("canonical position_seconds must be globally increasing")
            previous_position = position
            if mission != active_mission:
                if mission in seen_missions:
                    raise TelemetryFileError("canonical missions must occupy contiguous blocks")
                if active_mission is not None and mission <= active_mission:
                    raise TelemetryFileError("canonical mission_index must increase between blocks")
                seen_missions.add(mission)
                active_mission = mission
                origins[mission] = position
            observed_at = _observed_at(position)
            values = {field: _optional_finite(record[field], field) for field in RAW_SIGNAL_FIELDS}
            if start <= observed_at <= end:
                yield PersistedTelemetrySample(
                    mission_index=mission,
                    mission_origin_position_deciseconds=origins[mission],
                    position_deciseconds=position,
                    source_row=source_row,
                    observed_at_utc=observed_at,
                    values=values,
                )


def _original_zip_samples(path: Path, start: datetime, end: datetime) -> Iterator[PersistedTelemetrySample]:
    with zipfile.ZipFile(path) as archive:
        members = [name for name in archive.namelist() if Path(name).name == ORIGINAL_MEMBER_BASENAME]
        if len(members) != 1:
            raise TelemetryFileError("ZIP must contain exactly one Fendt 314.csv member")
        with archive.open(members[0], "r") as binary:
            handle = _text_wrapper(binary)
            try:
                yield from _original_rows(handle, start, end)
            finally:
                handle.detach()


def _text_wrapper(binary) -> TextIO:
    import io

    return io.TextIOWrapper(binary, encoding="utf-8-sig", newline="")


def _original_rows(handle: TextIO, start: datetime, end: datetime) -> Iterator[PersistedTelemetrySample]:
    header = handle.readline()
    if not header:
        raise TelemetryFileError("Fendt CSV is empty")
    delimiter = ";" if header.count(";") > header.count(",") else ","
    headers = tuple(next(csv.reader([header], delimiter=delimiter)))
    required = {"Time_(s)", "index_[-]", "Tractor_Model_[-]", *ORIGINAL_SIGNAL_COLUMNS}
    missing = sorted(required - set(headers))
    if missing:
        raise TelemetryFileError("Fendt CSV is missing required columns: " + ", ".join(missing))
    reader = csv.DictReader(handle, fieldnames=headers, delimiter=delimiter)
    previous_position: int | None = None
    mission = 0
    mission_origin: int | None = None
    previous_source_row: int | None = None
    for record in reader:
        position = _duration_deciseconds(record["Time_(s)"], "Time_(s)")
        source_row = _non_negative_int(record["index_[-]"], "index_[-]")
        if previous_source_row is not None and source_row <= previous_source_row:
            raise TelemetryFileError("Fendt index_[-] must be strictly increasing")
        previous_source_row = source_row
        model = (record.get("Tractor_Model_[-]") or "").strip()
        if model and model != "Fendt 314":
            raise TelemetryFileError("Fendt source contains a different tractor model")
        if previous_position is not None:
            if position <= previous_position:
                raise TelemetryFileError("Fendt Time_(s) must be globally increasing")
            if position - previous_position > 10:
                mission += 1
                mission_origin = position
        if mission_origin is None:
            mission_origin = position
        previous_position = position
        observed_at = _observed_at(position)
        # Preserve exactly the source's first observation and exact one-second
        # offsets from the real mission origin.  No line is interpolated.
        if (position - mission_origin) % 10 != 0:
            continue
        if not start <= observed_at <= end:
            continue
        values = {
            target: _optional_finite(record[source], source)
            for source, target in ORIGINAL_SIGNAL_COLUMNS.items()
        }
        yield PersistedTelemetrySample(
            mission_index=mission,
            mission_origin_position_deciseconds=mission_origin,
            position_deciseconds=position,
            source_row=source_row,
            observed_at_utc=observed_at,
            values=values,
        )


def _non_negative_int(value: str | None, name: str) -> int:
    try:
        parsed = int((value or "").strip())
    except ValueError as error:
        raise TelemetryFileError(f"{name} must be a non-negative integer") from error
    if parsed < 0:
        raise TelemetryFileError(f"{name} must be a non-negative integer")
    return parsed


def _deciseconds(value: str | None, name: str) -> int:
    text = (value or "").strip()
    if not text:
        raise TelemetryFileError(f"{name} must be finite and representable in deciseconds")
    # The original German export may use a decimal comma.  It is safe here
    # because fields are already split using a semicolon delimiter.
    normalized = text.replace(",", ".")
    try:
        decimal = Decimal(normalized)
    except InvalidOperation as error:
        raise TelemetryFileError(f"{name} must be finite and representable in deciseconds") from error
    if not decimal.is_finite() or decimal < 0:
        raise TelemetryFileError(f"{name} must be finite and representable in deciseconds")
    deciseconds = decimal * Decimal(10)
    if deciseconds != deciseconds.to_integral_value():
        raise TelemetryFileError(f"{name} must be representable in deciseconds")
    return int(deciseconds)


def _duration_deciseconds(value: str | None, name: str) -> int:
    """Parse the real export's ``N days HH:MM:SS.ffffff`` or numeric seconds."""

    text = (value or "").strip()
    if " day" not in text:
        return _deciseconds(text, name)
    parts = text.split()
    if len(parts) != 3 or parts[1] not in ("day", "days"):
        raise TelemetryFileError(f"{name} must be finite and representable in deciseconds")
    try:
        days = Decimal(parts[0])
        time_parts = parts[2].split(":")
        if len(time_parts) != 3:
            raise InvalidOperation
        hours, minutes, seconds = (Decimal(part) for part in time_parts)
    except (InvalidOperation, ValueError) as error:
        raise TelemetryFileError(
            f"{name} must be finite and representable in deciseconds"
        ) from error
    if (
        not all(value.is_finite() for value in (days, hours, minutes, seconds))
        or days < 0
        or hours < 0
        or hours >= 24
        or minutes < 0
        or minutes >= 60
        or seconds < 0
        or seconds >= 60
    ):
        raise TelemetryFileError(f"{name} must be finite and representable in deciseconds")
    total_seconds = days * Decimal(86_400) + hours * Decimal(3_600) + minutes * 60 + seconds
    deciseconds = total_seconds * Decimal(10)
    if deciseconds != deciseconds.to_integral_value():
        raise TelemetryFileError(f"{name} must be representable in deciseconds")
    return int(deciseconds)


def _optional_finite(value: str | None, name: str) -> float | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        parsed = float(text.replace(",", "."))
    except ValueError as error:
        raise TelemetryFileError(f"{name} must be finite when present") from error
    if not math.isfinite(parsed):
        raise TelemetryFileError(f"{name} must be finite when present")
    # IEEE-754 signed zero is numerically identical but has a distinct textual
    # representation. Canonicalize it so semantic identity cannot be bypassed.
    return 0.0 if parsed == 0.0 else parsed


def _observed_at(position_deciseconds: int) -> datetime:
    return EPOCH_UTC + timedelta(milliseconds=100 * position_deciseconds)


def _update_semantic_digest(digest, sample: PersistedTelemetrySample) -> None:
    material = {
        "mission_index": sample.mission_index,
        "mission_origin_position_deciseconds": sample.mission_origin_position_deciseconds,
        "position_deciseconds": sample.position_deciseconds,
        "source_row": sample.source_row,
        "values": [sample.values[field] for field in RAW_SIGNAL_FIELDS],
    }
    digest.update(json.dumps(material, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8"))
    digest.update(b"\n")
