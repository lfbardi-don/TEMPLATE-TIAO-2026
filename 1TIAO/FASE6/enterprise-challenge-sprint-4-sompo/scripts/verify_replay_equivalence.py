"""Verify that causal replay reproduces frozen batch windows and decisions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from tractor_usage.modeling.artifact import (
    ARTIFACT_FILENAME,
    MANIFEST_FILENAME,
    load_frozen_bundle,
)
from tractor_usage.modeling.hybrid import PHYSICAL_CONDITIONS
from tractor_usage.streaming.replay import CsvTelemetryReplay
from tractor_usage.streaming.windows import CausalWindowAggregator


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", required=True, type=Path)
    parser.add_argument("--windows", required=True, type=Path)
    parser.add_argument("--model-dir", required=True, type=Path)
    parser.add_argument("--mission-index", required=True, type=int)
    parser.add_argument("--split", required=True, choices=("train", "validation"))
    parser.add_argument("--tractor-id", default="fendt-314-equivalence")
    parser.add_argument("--absolute-tolerance", type=float, default=1e-9)
    return parser


def _ready_replay_windows(args: argparse.Namespace) -> tuple[pd.DataFrame, int]:
    source = CsvTelemetryReplay(
        args.samples,
        args.tractor_id,
        mission_index=args.mission_index,
    )
    aggregator = CausalWindowAggregator()
    frames: list[pd.DataFrame] = []
    no_data = 0
    for sample in source.iter_samples():
        for result in aggregator.ingest(sample):
            if result.status == "READY" and result.frame is not None:
                frames.append(result.frame)
            else:
                no_data += 1
    for result in aggregator.flush():
        if result.status == "READY" and result.frame is not None:
            frames.append(result.frame)
        else:
            no_data += 1
    if not frames:
        raise ValueError("replay produced no READY windows")
    return pd.concat(frames, ignore_index=True), no_data


def _aligned_frames(
    replayed: pd.DataFrame,
    reference: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    keys = ["mission_index", "window_index"]
    if replayed.duplicated(keys).any() or reference.duplicated(keys).any():
        raise ValueError("window identity must be unique in replay and reference")
    actual_keys = set(map(tuple, replayed[keys].itertuples(index=False, name=None)))
    expected_keys = set(map(tuple, reference[keys].itertuples(index=False, name=None)))
    if actual_keys != expected_keys:
        missing = sorted(expected_keys - actual_keys)
        unexpected = sorted(actual_keys - expected_keys)
        raise AssertionError(
            f"window identity mismatch; missing={missing}, unexpected={unexpected}"
        )
    replayed = replayed.sort_values(keys).reset_index(drop=True)
    reference = reference.sort_values(keys).reset_index(drop=True)
    return replayed, reference


def _assert_numeric_equivalence(
    replayed: pd.DataFrame,
    reference: pd.DataFrame,
    columns: list[str],
    absolute_tolerance: float,
) -> float:
    maximum_difference = 0.0
    for column in columns:
        difference = 0.0
        actual = pd.to_numeric(replayed[column], errors="coerce").to_numpy(float)
        expected = pd.to_numeric(reference[column], errors="coerce").to_numpy(float)
        if not np.array_equal(np.isnan(actual), np.isnan(expected)):
            raise AssertionError(f"NaN locations differ for {column}")
        finite = np.isfinite(actual) & np.isfinite(expected)
        if finite.any():
            difference = float(np.max(np.abs(actual[finite] - expected[finite])))
            maximum_difference = max(maximum_difference, difference)
        if not np.allclose(
            actual,
            expected,
            rtol=0.0,
            atol=absolute_tolerance,
            equal_nan=True,
        ):
            raise AssertionError(
                f"numeric replay mismatch for {column}; max_abs_diff={difference}"
            )
    return maximum_difference


def main() -> None:
    args = _parser().parse_args()
    if args.absolute_tolerance <= 0:
        raise ValueError("absolute-tolerance must be positive")

    batch = pd.read_csv(args.windows)
    mission = batch.loc[batch["mission_index"].eq(args.mission_index)].copy()
    if mission.empty:
        raise ValueError("mission is absent from the reference window dataset")
    mission_splits = set(mission["split"].dropna().astype(str))
    if mission_splits != {args.split}:
        raise ValueError(
            f"mission must belong only to requested split; found={sorted(mission_splits)}"
        )
    reference = mission.loc[mission["split"].eq(args.split)].copy()
    reference.insert(0, "tractor_id", args.tractor_id)

    replayed, no_data_windows = _ready_replay_windows(args)
    replayed, reference = _aligned_frames(replayed, reference)

    bundle = load_frozen_bundle(
        args.model_dir / ARTIFACT_FILENAME,
        args.model_dir / MANIFEST_FILENAME,
    )
    physical_columns = [column for _, column in PHYSICAL_CONDITIONS]
    numeric_columns = [
        "sample_count",
        "position_start",
        "position_end",
        "span_seconds",
        *bundle.feature_columns,
        *physical_columns,
        "severe_exposure__sum",
    ]
    maximum_difference = _assert_numeric_equivalence(
        replayed,
        reference,
        numeric_columns,
        args.absolute_tolerance,
    )
    expected_times = pd.DatetimeIndex(
        pd.to_datetime(reference["observed_at_utc"], utc=True)
    ).as_unit("ns")
    actual_times = pd.DatetimeIndex(
        pd.to_datetime(replayed["observed_at_utc"], utc=True)
    ).as_unit("ns")
    if not np.array_equal(actual_times.asi8, expected_times.asi8):
        mismatch = np.flatnonzero(actual_times.asi8 != expected_times.asi8)[0]
        raise AssertionError(
            "replayed observed_at_utc differs from batch reference at "
            f"row={int(mismatch)} actual={actual_times[mismatch].isoformat()} "
            f"expected={expected_times[mismatch].isoformat()} "
            f"delta_ns={int(actual_times.asi8[mismatch] - expected_times.asi8[mismatch])}"
        )

    expected_scored = bundle.score_windows(reference)
    replayed_scored = bundle.score_windows(replayed)
    for column in ("operational_regime", "physical_eligible", "hybrid_alert"):
        if not replayed_scored[column].equals(expected_scored[column]):
            raise AssertionError(f"scored decision mismatch for {column}")
    decision_difference = _assert_numeric_equivalence(
        replayed_scored,
        expected_scored,
        ["contextual_rarity_score", "contextual_rarity_threshold"],
        args.absolute_tolerance,
    )

    quality_counts = replayed["window_quality"].value_counts().sort_index().to_dict()
    summary = {
        "status": "PASS",
        "split": args.split,
        "mission_index": args.mission_index,
        "model_version": bundle.model_version,
        "ready_windows": len(replayed),
        "no_data_windows": no_data_windows,
        "alert_windows": int(replayed_scored["hybrid_alert"].sum()),
        "quality_counts": quality_counts,
        "compared_numeric_fields": len(numeric_columns),
        "maximum_feature_abs_difference": maximum_difference,
        "maximum_decision_abs_difference": decision_difference,
        "consumed_test_used": False,
    }
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
