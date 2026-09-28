"""Canonical one-second CSV replay adapter for observed Fendt telemetry."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import pandas as pd


FENDT_314_EPOCH_UTC = pd.Timestamp("2024-04-26T13:22:25.100Z")
CONSUMED_TEST_START_UTC = pd.Timestamp("2024-10-21T00:00:00Z")

RAW_SIGNAL_FIELDS = (
    "engine_rpm",
    "actual_engine_torque_pct",
    "engine_load_pct",
    "accelerator_pct",
    "coolant_temp_c",
    "front_axle_speed_kph",
    "speed_over_ground_mps",
    "ground_implement_speed_mmps",
    "wheel_vehicle_speed_kph",
    "rear_pto_rpm",
    "rear_hitch_position",
    "rear_hitch_in_work",
    "rear_link_force_pct",
    "rear_draft_n",
    "ground_machine_speed_mps",
    "machine_selected_speed_mps",
    "wheel_machine_speed_mps",
)

REPLAY_COLUMNS = (
    "mission_index",
    "position_seconds",
    "source_row",
    *RAW_SIGNAL_FIELDS,
)


def _optional_float(value: object) -> float | None:
    if pd.isna(value):
        return None
    return float(value)


@dataclass(frozen=True)
class TelemetrySample:
    tractor_id: str
    mission_index: int
    mission_elapsed_seconds: float
    position_seconds: float
    source_row: int
    observed_at_utc: pd.Timestamp
    engine_rpm: float | None
    actual_engine_torque_pct: float | None
    engine_load_pct: float | None
    accelerator_pct: float | None
    coolant_temp_c: float | None
    front_axle_speed_kph: float | None
    speed_over_ground_mps: float | None
    ground_implement_speed_mmps: float | None
    wheel_vehicle_speed_kph: float | None
    rear_pto_rpm: float | None
    rear_hitch_position: float | None
    rear_hitch_in_work: float | None
    rear_link_force_pct: float | None
    rear_draft_n: float | None
    ground_machine_speed_mps: float | None
    machine_selected_speed_mps: float | None
    wheel_machine_speed_mps: float | None


class CsvTelemetryReplay:
    """Yield ordered observed samples without loading the full CSV into memory."""

    def __init__(
        self,
        path: Path,
        tractor_id: str,
        *,
        mission_index: int | None = None,
        allow_consumed_test: bool = False,
        chunksize: int = 50_000,
    ) -> None:
        if not tractor_id.strip():
            raise ValueError("tractor_id must not be empty")
        if chunksize <= 0:
            raise ValueError("chunksize must be positive")
        self.path = path
        self.tractor_id = tractor_id
        self.mission_index = mission_index
        self.allow_consumed_test = allow_consumed_test
        self.chunksize = chunksize

    def iter_samples(self) -> Iterator[TelemetrySample]:
        previous_position: float | None = None
        mission_origins: dict[int, float] = {}
        seen_keys: set[tuple[int, float]] = set()

        for chunk in pd.read_csv(
            self.path,
            usecols=list(REPLAY_COLUMNS),
            chunksize=self.chunksize,
        ):
            missing = sorted(set(REPLAY_COLUMNS) - set(chunk.columns))
            if missing:
                raise ValueError(f"missing replay columns: {', '.join(missing)}")
            for row in chunk.itertuples(index=False):
                mission = int(row.mission_index)
                if self.mission_index is not None and mission != self.mission_index:
                    continue
                position = float(row.position_seconds)
                if previous_position is not None and position <= previous_position:
                    raise ValueError("replay position_seconds must be strictly increasing")
                key = (mission, position)
                if key in seen_keys:
                    raise ValueError("duplicate canonical replay sample")
                seen_keys.add(key)
                previous_position = position
                origin = mission_origins.setdefault(mission, position)
                elapsed = position - origin
                if elapsed < 0:
                    raise ValueError("mission elapsed time cannot be negative")
                observed_at = FENDT_314_EPOCH_UTC + pd.to_timedelta(
                    position, unit="s"
                )
                if not self.allow_consumed_test and observed_at >= CONSUMED_TEST_START_UTC:
                    raise ValueError("official replay cannot access the consumed test period")

                values = {
                    field: _optional_float(getattr(row, field))
                    for field in RAW_SIGNAL_FIELDS
                }
                yield TelemetrySample(
                    tractor_id=self.tractor_id,
                    mission_index=mission,
                    mission_elapsed_seconds=elapsed,
                    position_seconds=position,
                    source_row=int(row.source_row),
                    observed_at_utc=observed_at,
                    **values,
                )
