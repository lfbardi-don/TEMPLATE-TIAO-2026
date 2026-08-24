"""Versioned, integrity-checked persistence for the approved model bundle."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from hashlib import sha256
from importlib.metadata import version as package_version
import json
import os
from pathlib import Path
import platform
from typing import Any

import joblib
import numpy as np
import pandas as pd

from tractor_usage.modeling.hybrid import (
    HybridCandidateMetrics,
    HybridUsageModel,
)
from tractor_usage.modeling.longitudinal import (
    LongitudinalBaseline,
    LongitudinalScore,
    aggregate_integrity_horizons,
)


FROZEN_MODEL_VERSION = "fendt314-hybrid-v2.0.1"
FROZEN_CONTRACT_VERSION = "window-inference-v1.1"
FROZEN_FEATURE_SCHEMA = "usage_context_v2"
FROZEN_PHYSICAL_RULES = "physical_rules_v1"
ARTIFACT_FILENAME = "bundle.joblib"
MANIFEST_FILENAME = "manifest.json"
WINDOW_SPAN_TOLERANCE_SECONDS = 1e-6


@dataclass(frozen=True)
class FrozenProvenance:
    created_at_utc: str
    train_start_utc: str
    train_end_utc: str
    train_windows: int
    validation_start_utc: str
    validation_end_utc: str
    validation_windows: int
    final_test_decision: str = "GO"
    test_split_consumed: bool = True
    test_data_used_for_fit: bool = False
    test_data_scored_during_freeze: bool = False


@dataclass(frozen=True)
class FrozenUsageBundle:
    model_version: str
    contract_version: str
    feature_schema: str
    physical_rules_version: str
    feature_columns: tuple[str, ...]
    model: HybridUsageModel
    longitudinal_baseline: LongitudinalBaseline
    provenance: FrozenProvenance
    validation_metrics: HybridCandidateMetrics
    integrity_fingerprint: str = ""

    def score_windows(self, frame: pd.DataFrame) -> pd.DataFrame:
        """Score complete window rows at the stable bundle boundary."""

        _assert_approved_identity(self)
        _assert_bundle_integrity(self)
        if "tractor_id" not in frame:
            raise ValueError("tractor_id is required for bundle inference")
        tractor_id = frame["tractor_id"].astype("string")
        if tractor_id.isna().any() or tractor_id.str.strip().eq("").any():
            raise ValueError("tractor_id must contain stable non-empty identifiers")
        missing_features = sorted(set(self.feature_columns) - set(frame.columns))
        if missing_features:
            raise ValueError(
                f"missing frozen model features: {', '.join(missing_features)}"
            )
        if "sample_count" not in frame:
            raise ValueError("sample_count is required for bundle inference")
        if "span_seconds" not in frame:
            raise ValueError("span_seconds is required for bundle inference")
        sample_count = pd.to_numeric(frame["sample_count"], errors="coerce")
        span_seconds = pd.to_numeric(frame["span_seconds"], errors="coerce")
        sample_count_values = sample_count.to_numpy(dtype=float)
        span_seconds_values = span_seconds.to_numpy(dtype=float)
        if (
            not np.isfinite(sample_count_values).all()
            or not np.equal(sample_count_values, np.floor(sample_count_values)).all()
        ):
            raise ValueError("sample_count must contain finite whole-number values")
        if not np.isfinite(span_seconds_values).all():
            raise ValueError("span_seconds must contain finite numeric values")
        standard_window = (
            sample_count.between(55, 60)
            & span_seconds.between(54.0, 60.0 + WINDOW_SPAN_TOLERANCE_SECONDS)
        )
        boundary_jitter_window = (
            sample_count.eq(61)
            & span_seconds.between(59.0, 60.0 + WINDOW_SPAN_TOLERANCE_SECONDS)
        )
        if not (standard_window | boundary_jitter_window).all():
            raise ValueError(
                "sample_count/span_seconds must form a complete inference window"
            )
        if "window_quality" in frame:
            expected_quality = np.select(
                [boundary_jitter_window, sample_count.eq(60)],
                ["boundary_jitter", "complete"],
                default="partial_coverage",
            )
            supplied_quality = frame["window_quality"].astype("string")
            if supplied_quality.isna().any() or not np.array_equal(
                supplied_quality.to_numpy(dtype=str),
                expected_quality,
            ):
                raise ValueError(
                    "window_quality must match the validated sample count and span"
                )
        scored = self.model.score(frame)
        scored.insert(0, "model_version", self.model_version)
        if "window_quality" in frame:
            scored["window_quality"] = frame["window_quality"].to_numpy()
        return scored

    def aggregate(
        self,
        scored_history: pd.DataFrame,
        as_of_utc: str | pd.Timestamp,
    ) -> tuple[LongitudinalScore, ...]:
        _assert_approved_identity(self)
        _assert_bundle_integrity(self)
        return aggregate_integrity_horizons(
            scored_history,
            as_of_utc,
            self.longitudinal_baseline,
        )


def _runtime_integrity_fingerprint(bundle: FrozenUsageBundle) -> str:
    """Fingerprint mutable in-memory state; reestablished after deserialization."""

    return joblib.hash((bundle.model, bundle.longitudinal_baseline))


def _with_integrity_fingerprint(bundle: FrozenUsageBundle) -> FrozenUsageBundle:
    return FrozenUsageBundle(
        model_version=bundle.model_version,
        contract_version=bundle.contract_version,
        feature_schema=bundle.feature_schema,
        physical_rules_version=bundle.physical_rules_version,
        feature_columns=bundle.feature_columns,
        model=bundle.model,
        longitudinal_baseline=bundle.longitudinal_baseline,
        provenance=bundle.provenance,
        validation_metrics=bundle.validation_metrics,
        integrity_fingerprint=_runtime_integrity_fingerprint(bundle),
    )


def _assert_bundle_integrity(bundle: FrozenUsageBundle) -> None:
    if not bundle.integrity_fingerprint:
        raise ValueError("frozen bundle integrity fingerprint is unavailable")
    if bundle.integrity_fingerprint != _runtime_integrity_fingerprint(bundle):
        raise ValueError("frozen bundle model state changed after construction")


def _require_utc(value: str, field: str) -> None:
    timestamp = pd.Timestamp(value)
    if pd.isna(timestamp) or timestamp.tzinfo is None:
        raise ValueError(f"{field} must be timezone-aware")


def _assert_approved_identity(bundle: FrozenUsageBundle) -> None:
    if bundle.model_version != FROZEN_MODEL_VERSION:
        raise ValueError("unexpected frozen model version")
    if bundle.contract_version != FROZEN_CONTRACT_VERSION:
        raise ValueError("unexpected inference contract version")
    if bundle.feature_schema != FROZEN_FEATURE_SCHEMA:
        raise ValueError("unexpected feature schema")
    if bundle.physical_rules_version != FROZEN_PHYSICAL_RULES:
        raise ValueError("unexpected physical rules version")
    if bundle.feature_columns != bundle.model.regime_model.feature_columns:
        raise ValueError("bundle feature order differs from fitted regime model")
    if bundle.model.regime_model.kind != "kmeans":
        raise ValueError("approved bundle requires K-Means regimes")
    if bundle.model.regime_model.components != 3:
        raise ValueError("approved bundle requires exactly three regimes")
    if bundle.model.kind != "isolation_forest":
        raise ValueError("approved bundle requires Isolation Forest rarity")
    if bundle.model.threshold_quantile != 0.97:
        raise ValueError("approved bundle requires the 0.97 training quantile")
    if bundle.model.minimum_physical_seconds != 5.0:
        raise ValueError("approved bundle requires minimum_physical_seconds=5.0")
    if set(bundle.model.detectors) != {0, 1, 2}:
        raise ValueError("approved bundle requires one detector for each regime")
    if set(bundle.model.thresholds) != {0, 1, 2}:
        raise ValueError("approved bundle requires one threshold for each regime")
    if not bundle.validation_metrics.passes_gate:
        raise ValueError("approved bundle requires passing validation metrics")
    if bundle.provenance.test_data_used_for_fit:
        raise ValueError("test data must not be used for bundle fitting")
    if bundle.provenance.test_data_scored_during_freeze:
        raise ValueError("freeze workflow must not score consumed test data")
    for field in (
        "created_at_utc",
        "train_start_utc",
        "train_end_utc",
        "validation_start_utc",
        "validation_end_utc",
    ):
        _require_utc(getattr(bundle.provenance, field), field)


def build_frozen_bundle(
    model: HybridUsageModel,
    longitudinal_baseline: LongitudinalBaseline,
    provenance: FrozenProvenance,
    validation_metrics: HybridCandidateMetrics,
) -> FrozenUsageBundle:
    """Construct the approved typed bundle and reject identity drift."""

    bundle = FrozenUsageBundle(
        model_version=FROZEN_MODEL_VERSION,
        contract_version=FROZEN_CONTRACT_VERSION,
        feature_schema=FROZEN_FEATURE_SCHEMA,
        physical_rules_version=FROZEN_PHYSICAL_RULES,
        feature_columns=model.regime_model.feature_columns,
        model=model,
        longitudinal_baseline=longitudinal_baseline,
        provenance=provenance,
        validation_metrics=validation_metrics,
    )
    _assert_approved_identity(bundle)
    return _with_integrity_fingerprint(bundle)


def sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _runtime_versions() -> dict[str, str]:
    return {
        "python": platform.python_version(),
        "joblib": package_version("joblib"),
        "numpy": package_version("numpy"),
        "pandas": package_version("pandas"),
        "scikit-learn": package_version("scikit-learn"),
    }


def _manifest(
    bundle: FrozenUsageBundle,
    *,
    artifact_sha256: str,
    artifact_size_bytes: int,
    source_windows_sha256: str,
) -> dict[str, Any]:
    return {
        "model_version": bundle.model_version,
        "contract_version": bundle.contract_version,
        "feature_schema": bundle.feature_schema,
        "physical_rules_version": bundle.physical_rules_version,
        "artifact_filename": ARTIFACT_FILENAME,
        "artifact_sha256": artifact_sha256,
        "artifact_size_bytes": artifact_size_bytes,
        "source_windows_sha256": source_windows_sha256,
        "runtime": _runtime_versions(),
        "feature_columns": list(bundle.feature_columns),
        "frozen_model": _frozen_model_manifest(bundle),
        "provenance": asdict(bundle.provenance),
        "validation_metrics": bundle.validation_metrics.to_dict(),
    }


def _frozen_model_manifest(bundle: FrozenUsageBundle) -> dict[str, object]:
    return {
        "regime_kind": bundle.model.regime_model.kind,
        "regime_components": bundle.model.regime_model.components,
        "rarity_kind": bundle.model.kind,
        "threshold_quantile": bundle.model.threshold_quantile,
        "minimum_physical_seconds": bundle.model.minimum_physical_seconds,
        "longitudinal_horizons": sorted(
            bundle.longitudinal_baseline.component_distributions
        ),
    }


def _assert_manifest_matches_bundle(
    manifest: dict[str, Any],
    bundle: FrozenUsageBundle,
    model_path: Path,
) -> None:
    expected = {
        "model_version": bundle.model_version,
        "contract_version": bundle.contract_version,
        "feature_schema": bundle.feature_schema,
        "physical_rules_version": bundle.physical_rules_version,
        "artifact_filename": model_path.name,
        "feature_columns": list(bundle.feature_columns),
        "frozen_model": _frozen_model_manifest(bundle),
        "provenance": asdict(bundle.provenance),
        "validation_metrics": bundle.validation_metrics.to_dict(),
    }
    for field, value in expected.items():
        if manifest.get(field) != value:
            raise ValueError(f"manifest {field} differs from frozen bundle")


def save_frozen_bundle(
    bundle: FrozenUsageBundle,
    output_dir: Path,
    source_windows_sha256: str,
) -> dict[str, Any]:
    """Atomically write a new bundle and versionable integrity manifest."""

    _assert_approved_identity(bundle)
    _assert_bundle_integrity(bundle)
    if len(source_windows_sha256) != 64:
        raise ValueError("source_windows_sha256 must be a SHA-256 hex digest")
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = output_dir / ARTIFACT_FILENAME
    manifest_path = output_dir / MANIFEST_FILENAME
    if artifact_path.exists() or manifest_path.exists():
        raise FileExistsError("frozen bundle output already exists; overwrite refused")

    temporary_artifact = output_dir / f".{ARTIFACT_FILENAME}.tmp"
    temporary_manifest = output_dir / f".{MANIFEST_FILENAME}.tmp"
    if temporary_artifact.exists() or temporary_manifest.exists():
        raise FileExistsError("temporary frozen bundle output already exists")

    try:
        joblib.dump(bundle, temporary_artifact, compress=3)
        artifact_digest = sha256_file(temporary_artifact)
        manifest = _manifest(
            bundle,
            artifact_sha256=artifact_digest,
            artifact_size_bytes=temporary_artifact.stat().st_size,
            source_windows_sha256=source_windows_sha256,
        )
        temporary_manifest.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        )
        os.replace(temporary_artifact, artifact_path)
        os.replace(temporary_manifest, manifest_path)
    except BaseException:
        artifact_path.unlink(missing_ok=True)
        manifest_path.unlink(missing_ok=True)
        raise
    finally:
        temporary_artifact.unlink(missing_ok=True)
        temporary_manifest.unlink(missing_ok=True)
    return manifest


def load_frozen_bundle(
    model_path: Path,
    manifest_path: Path,
) -> FrozenUsageBundle:
    """Load only a trusted local artifact after integrity verification."""

    manifest = json.loads(manifest_path.read_text())
    if manifest.get("model_version") != FROZEN_MODEL_VERSION:
        raise ValueError("manifest model version is not approved")
    if manifest.get("contract_version") != FROZEN_CONTRACT_VERSION:
        raise ValueError("manifest contract version is not approved")
    if manifest.get("artifact_filename") != model_path.name:
        raise ValueError("manifest artifact filename does not match model path")
    if manifest.get("artifact_size_bytes") != model_path.stat().st_size:
        raise ValueError("frozen artifact size differs from manifest")
    if manifest.get("artifact_sha256") != sha256_file(model_path):
        raise ValueError("frozen artifact SHA-256 differs from manifest")

    loaded = joblib.load(model_path)
    if not isinstance(loaded, FrozenUsageBundle):
        raise ValueError("artifact does not contain a FrozenUsageBundle")
    _assert_approved_identity(loaded)
    # Artifact SHA-256 and manifest authenticate the serialized bytes. The
    # runtime fingerprint is intentionally reestablished because joblib.hash
    # is not stable across a normal serialization round trip.
    loaded = _with_integrity_fingerprint(loaded)
    _assert_manifest_matches_bundle(manifest, loaded, model_path)
    return loaded


def verify_bundle_equivalence(
    original: FrozenUsageBundle,
    loaded: FrozenUsageBundle,
    validation: pd.DataFrame,
) -> None:
    """Assert semantic equivalence after serialization on non-test windows."""

    original_scored = original.score_windows(validation)
    loaded_scored = loaded.score_windows(validation)
    for column in (
        "operational_regime",
        "physical_eligible",
        "hybrid_alert",
        "hybrid_episode_start",
    ):
        if not original_scored[column].equals(loaded_scored[column]):
            raise ValueError(f"loaded bundle changed {column}")
    for column in ("contextual_rarity_score", "contextual_rarity_threshold"):
        if not np.allclose(
            original_scored[column].to_numpy(dtype=float),
            loaded_scored[column].to_numpy(dtype=float),
            rtol=0.0,
            atol=1e-12,
        ):
            raise ValueError(f"loaded bundle changed {column}")
