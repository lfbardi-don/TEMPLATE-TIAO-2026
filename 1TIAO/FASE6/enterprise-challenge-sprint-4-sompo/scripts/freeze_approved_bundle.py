"""Freeze the approved V2 model without scoring the consumed test split."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import pandas as pd

from tractor_usage.experiments.selection import run_selection, selection_splits
from tractor_usage.modeling.artifact import (
    ARTIFACT_FILENAME,
    MANIFEST_FILENAME,
    FrozenProvenance,
    build_frozen_bundle,
    load_frozen_bundle,
    save_frozen_bundle,
    sha256_file,
    verify_bundle_equivalence,
)
from tractor_usage.modeling.hybrid import audit_scored_hybrid
from tractor_usage.modeling.longitudinal import fit_longitudinal_baseline


def freeze_approved_bundle(
    windows_path: Path,
    output_dir: Path,
) -> dict[str, object]:
    frame = pd.read_csv(windows_path)
    frame["observed_at_utc"] = pd.to_datetime(
        frame["observed_at_utc"], format="mixed", utc=True
    )
    frame = frame.sort_values("observed_at_utc", kind="stable").reset_index(drop=True)
    report, model = run_selection(frame)
    if model is None or not report["regime"]["accepted"] or not report["hybrid"]["accepted"]:
        raise RuntimeError("approved validation candidate was not reconstructed")
    if report["test"] != {"status": "CLOSED", "scored": False}:
        raise RuntimeError("freeze workflow unexpectedly opened the test split")

    selected = report["hybrid"]["selected"]
    expected_identity = {
        "kind": "isolation_forest",
        "threshold_quantile": 0.97,
    }
    if any(selected[key] != value for key, value in expected_identity.items()):
        raise RuntimeError("reconstructed candidate differs from approved identity")
    if model.regime_model.kind != "kmeans" or model.regime_model.components != 3:
        raise RuntimeError("reconstructed regime model differs from approved identity")

    train, validation = selection_splits(frame)
    scored_train = model.score(train)
    baseline = fit_longitudinal_baseline(scored_train)
    validation_metrics = audit_scored_hybrid(
        validation,
        model.score(validation),
        model,
    )
    if not validation_metrics.passes_gate:
        raise RuntimeError("reconstructed candidate no longer passes validation")

    train_time = pd.to_datetime(train["observed_at_utc"], utc=True)
    validation_time = pd.to_datetime(validation["observed_at_utc"], utc=True)
    provenance = FrozenProvenance(
        created_at_utc=datetime.now(timezone.utc).isoformat(),
        train_start_utc=train_time.min().isoformat(),
        train_end_utc=train_time.max().isoformat(),
        train_windows=len(train),
        validation_start_utc=validation_time.min().isoformat(),
        validation_end_utc=validation_time.max().isoformat(),
        validation_windows=len(validation),
    )
    bundle = build_frozen_bundle(
        model,
        baseline,
        provenance,
        validation_metrics,
    )
    manifest = save_frozen_bundle(
        bundle,
        output_dir,
        sha256_file(windows_path),
    )
    loaded = load_frozen_bundle(
        output_dir / ARTIFACT_FILENAME,
        output_dir / MANIFEST_FILENAME,
    )
    verification_frame = validation.copy()
    verification_frame.insert(0, "tractor_id", "fendt-314-public-dataset")
    verify_bundle_equivalence(bundle, loaded, verification_frame)

    return {
        "model_version": bundle.model_version,
        "artifact_sha256": manifest["artifact_sha256"],
        "source_windows_sha256": manifest["source_windows_sha256"],
        "validation_windows_verified": len(verification_frame),
        "test_data_used_for_fit": False,
        "test_data_scored_during_freeze": False,
        "round_trip_equivalent": True,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--windows", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    return parser


def main() -> None:
    args = _parser().parse_args()
    summary = freeze_approved_bundle(args.windows, args.output_dir)
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
