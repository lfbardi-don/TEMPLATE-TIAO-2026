from pathlib import Path
import json

import numpy as np
import pandas as pd
import pytest
from sklearn.cluster import KMeans
from sklearn.ensemble import IsolationForest
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import RobustScaler

from tractor_usage.modeling.artifact import (
    ARTIFACT_FILENAME,
    FROZEN_CONTRACT_VERSION,
    FROZEN_MODEL_VERSION,
    MANIFEST_FILENAME,
    FrozenProvenance,
    build_frozen_bundle,
    load_frozen_bundle,
    save_frozen_bundle,
    verify_bundle_equivalence,
)
from tractor_usage.modeling.hybrid import (
    HybridCandidateMetrics,
    HybridUsageModel,
)
from tractor_usage.modeling.longitudinal import LongitudinalBaseline
from tractor_usage.modeling.regimes import RegimeModel
from tractor_usage.streaming.replay import RAW_SIGNAL_FIELDS, TelemetrySample
from tractor_usage.streaming.windows import CausalWindowAggregator


def _approved_bundle(*, minimum_physical_seconds: float = 5.0):
    rng = np.random.default_rng(21)
    values = np.vstack(
        [
            rng.normal(-4.0, 0.2, (40, 3)),
            rng.normal(0.0, 0.2, (40, 3)),
            rng.normal(4.0, 0.2, (40, 3)),
        ]
    )
    frame = pd.DataFrame(values, columns=["a", "b", "c"])
    preprocessor = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", RobustScaler()),
        ]
    )
    transformed = preprocessor.fit_transform(frame)
    estimator = KMeans(n_clusters=3, n_init=20, random_state=0).fit(transformed)
    labels = estimator.predict(transformed)
    detectors = {}
    thresholds = {}
    medians = {}
    iqrs = {}
    for regime in range(3):
        regime_values = transformed[labels == regime]
        detector = IsolationForest(n_estimators=10, random_state=0).fit(
            regime_values
        )
        scores = -detector.score_samples(regime_values)
        detectors[regime] = detector
        thresholds[regime] = float(np.quantile(scores, 0.97))
        medians[regime] = np.median(regime_values, axis=0)
        q75, q25 = np.percentile(regime_values, [75, 25], axis=0)
        iqrs[regime] = np.maximum(q75 - q25, 1e-6)

    regime_model = RegimeModel(
        kind="kmeans",
        components=3,
        feature_columns=("a", "b", "c"),
        preprocessor=preprocessor,
        estimator=estimator,
        regime_reasons={0: ("a", "b", "c"), 1: ("a", "b", "c"), 2: ("a", "b", "c")},
    )
    model = HybridUsageModel(
        kind="isolation_forest",
        threshold_quantile=0.97,
        regime_model=regime_model,
        detectors=detectors,
        thresholds=thresholds,
        reference_median=medians,
        reference_iqr=iqrs,
        minimum_physical_seconds=minimum_physical_seconds,
    )
    baseline = LongitudinalBaseline(
        {
            horizon: {
                "physical_exposure_seconds_per_hour": (0.0, 10.0),
                "alert_exposure_seconds_per_hour": (0.0, 5.0),
                "episodes_per_hour": (0.0, 1.0),
            }
            for horizon in (7, 15, 30)
        }
    )
    provenance = FrozenProvenance(
        created_at_utc="2026-08-22T12:00:00+00:00",
        train_start_utc="2024-04-26T13:25:49+00:00",
        train_end_utc="2024-09-05T23:00:00+00:00",
        train_windows=120,
        validation_start_utc="2024-09-06T00:00:00+00:00",
        validation_end_utc="2024-10-20T00:00:00+00:00",
        validation_windows=60,
    )
    metrics = HybridCandidateMetrics(
        kind="isolation_forest",
        threshold_quantile=0.97,
        alert_fraction=0.03,
        physical_eligible_fraction=0.40,
        contextual_retention=0.075,
        represented_families=3,
        alert_windows_by_family={"lugging": 5, "overload_torque": 5, "harsh_torque_rise": 5},
        episodes=10,
        episodes_per_observed_hour=1.0,
        active_alert_dates=5,
        maximum_daily_episode_share=0.30,
        explanations_complete=True,
        passes_gate=True,
    )
    return build_frozen_bundle(model, baseline, provenance, metrics)


def _all_lugging_boundary_sample(second: int) -> TelemetrySample:
    position = float(second)
    mission_elapsed = float(second) if second < 60 else 59.999999
    signals = {field: 0.0 for field in RAW_SIGNAL_FIELDS}
    signals.update(
        {
            "engine_rpm": 1200.0,
            "actual_engine_torque_pct": 10.0,
            "engine_load_pct": 80.0,
        }
    )
    return TelemetrySample(
        tractor_id="tractor-1",
        mission_index=1,
        mission_elapsed_seconds=mission_elapsed,
        position_seconds=position,
        source_row=second,
        observed_at_utc=pd.Timestamp("2024-11-01T00:00:00Z")
        + pd.Timedelta(seconds=position),
        **signals,
    )


def _inference_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "tractor_id": ["tractor-1", "tractor-1"],
            "observed_at_utc": pd.date_range(
                "2024-11-01T00:00:00Z", periods=2, freq="min"
            ),
            "mission_index": [1, 1],
            "window_index": [0, 1],
            "sample_count": [60, 60],
            "span_seconds": [59.0, 59.0],
            "window_quality": ["complete", "complete"],
            "a": [0.0, 4.0],
            "b": [0.0, 4.0],
            "c": [0.0, 4.0],
            "lugging__sum": [0.0, 8.0],
            "overload_torque__sum": [0.0, 8.0],
            "loaded_high_slip__sum": [0.0, 0.0],
            "thermal_under_load__sum": [0.0, 0.0],
            "harsh_torque_rise__sum": [0.0, 0.0],
            "severe_exposure__sum": [0.0, 8.0],
        }
    )


def test_bundle_round_trip_and_overwrite_refusal(tmp_path: Path) -> None:
    bundle = _approved_bundle()

    manifest = save_frozen_bundle(bundle, tmp_path, "a" * 64)
    loaded = load_frozen_bundle(
        tmp_path / ARTIFACT_FILENAME,
        tmp_path / MANIFEST_FILENAME,
    )
    verify_bundle_equivalence(bundle, loaded, _inference_frame())

    assert manifest["artifact_sha256"]
    assert loaded.model_version == "fendt314-hybrid-v2.0.1"
    assert loaded.model_version == FROZEN_MODEL_VERSION
    assert loaded.contract_version == FROZEN_CONTRACT_VERSION
    assert loaded.integrity_fingerprint
    with pytest.raises(FileExistsError, match="overwrite refused"):
        save_frozen_bundle(bundle, tmp_path, "a" * 64)


def test_tampered_bundle_refuses_load(tmp_path: Path) -> None:
    bundle = _approved_bundle()
    save_frozen_bundle(bundle, tmp_path, "b" * 64)
    artifact = tmp_path / ARTIFACT_FILENAME
    contents = bytearray(artifact.read_bytes())
    contents[0] ^= 1
    artifact.write_bytes(contents)

    with pytest.raises(ValueError, match="SHA-256"):
        load_frozen_bundle(artifact, tmp_path / MANIFEST_FILENAME)


def test_bundle_rejects_incomplete_or_missing_window_input() -> None:
    bundle = _approved_bundle()
    incomplete = _inference_frame()
    incomplete.loc[0, "sample_count"] = 54
    with pytest.raises(ValueError, match="sample_count/span_seconds"):
        bundle.score_windows(incomplete)

    missing = _inference_frame().drop(columns="a")
    with pytest.raises(ValueError, match="missing frozen model features"):
        bundle.score_windows(missing)


@pytest.mark.parametrize(
    ("sample_count", "span_seconds", "window_quality"),
    [
        (55, 54.0, "partial_coverage"),
        (60, 60.0 + 1e-6, "complete"),
        (61, 59.0, "boundary_jitter"),
    ],
)
def test_bundle_accepts_approved_sample_span_combinations(
    sample_count: int,
    span_seconds: float,
    window_quality: str,
) -> None:
    bundle = _approved_bundle()
    frame = _inference_frame().iloc[[0]].copy()
    frame.loc[:, "sample_count"] = sample_count
    frame.loc[:, "span_seconds"] = span_seconds
    frame.loc[:, "window_quality"] = window_quality

    scored = bundle.score_windows(frame)

    assert scored.loc[frame.index[0], "window_quality"] == window_quality


def test_bundle_rejects_missing_non_numeric_and_invalid_spans() -> None:
    bundle = _approved_bundle()

    missing_span = _inference_frame().drop(columns="span_seconds")
    with pytest.raises(ValueError, match="span_seconds is required"):
        bundle.score_windows(missing_span)

    non_numeric_span = _inference_frame()
    non_numeric_span["span_seconds"] = ["not-a-number", 59.0]
    with pytest.raises(ValueError, match="span_seconds must contain finite numeric"):
        bundle.score_windows(non_numeric_span)

    out_of_range_span = _inference_frame()
    out_of_range_span.loc[0, "span_seconds"] = 60.000002
    with pytest.raises(ValueError, match="sample_count/span_seconds"):
        bundle.score_windows(out_of_range_span)

    invalid_boundary_jitter_span = _inference_frame()
    invalid_boundary_jitter_span.loc[0, "sample_count"] = 61
    invalid_boundary_jitter_span.loc[0, "span_seconds"] = 58.0
    with pytest.raises(ValueError, match="sample_count/span_seconds"):
        bundle.score_windows(invalid_boundary_jitter_span)


def test_bundle_rejects_window_quality_that_conflicts_with_validated_shape() -> None:
    bundle = _approved_bundle()
    mismatched = _inference_frame().iloc[[0]].copy()
    mismatched.loc[:, "sample_count"] = 61
    mismatched.loc[:, "span_seconds"] = 60.0
    mismatched.loc[:, "window_quality"] = "complete"

    with pytest.raises(ValueError, match="window_quality must match"):
        bundle.score_windows(mismatched)


def test_boundary_jitter_aggregation_is_scoreable_at_sixty_seconds() -> None:
    aggregator = CausalWindowAggregator()
    for second in range(61):
        aggregator.ingest(_all_lugging_boundary_sample(second))
    result = aggregator.flush()[0]

    assert result.status == "READY"
    assert result.frame is not None
    assert result.frame.loc[0, "lugging__sum"] == 60.0
    assert result.frame.loc[0, "severe_exposure__sum"] == 60.0

    scoreable = result.frame.assign(a=0.0, b=0.0, c=0.0)
    scored = _approved_bundle().score_windows(scoreable)

    assert len(scored) == 1


def test_bundle_requires_exact_minimum_physical_seconds() -> None:
    with pytest.raises(ValueError, match="minimum_physical_seconds=5.0"):
        _approved_bundle(minimum_physical_seconds=4.0)

    bundle = _approved_bundle()
    bundle.model.minimum_physical_seconds = 4.0
    with pytest.raises(ValueError, match="minimum_physical_seconds=5.0"):
        bundle.score_windows(_inference_frame())


@pytest.mark.parametrize(
    ("mutation", "load_before_mutation"),
    [
        ("threshold", False),
        ("reference", True),
        ("estimator", True),
        ("baseline", True),
    ],
)
def test_bundle_detects_nested_runtime_mutation(
    tmp_path: Path,
    mutation: str,
    load_before_mutation: bool,
) -> None:
    bundle = _approved_bundle()
    if load_before_mutation:
        output_dir = tmp_path / mutation
        save_frozen_bundle(bundle, output_dir, "c" * 64)
        bundle = load_frozen_bundle(
            output_dir / ARTIFACT_FILENAME,
            output_dir / MANIFEST_FILENAME,
        )

    if mutation == "threshold":
        bundle.model.thresholds[0] += 1e-6
    elif mutation == "reference":
        bundle.model.reference_median[0][0] += 1e-6
    elif mutation == "estimator":
        bundle.model.regime_model.estimator.cluster_centers_[0, 0] += 1e-6
    else:
        bundle.longitudinal_baseline.component_distributions[7][
            "episodes_per_hour"
        ] = (99.0,)

    if mutation == "baseline":
        operation = lambda: bundle.aggregate(pd.DataFrame(), "2024-11-01T00:00:00Z")
    else:
        operation = lambda: bundle.score_windows(_inference_frame())
    with pytest.raises(ValueError, match="model state changed"):
        operation()


@pytest.mark.parametrize(
    "tamper",
    [
        "model_version",
        "contract_version",
        "feature_schema",
        "physical_rules_version",
        "artifact_filename",
        "artifact_size_bytes",
        "artifact_sha256",
        "feature_columns",
        "frozen_model",
        "provenance",
        "validation_metrics",
    ],
)
def test_load_rejects_manifest_bundle_disagreement_with_valid_binary(
    tmp_path: Path,
    tamper: str,
) -> None:
    bundle = _approved_bundle()
    save_frozen_bundle(bundle, tmp_path, "d" * 64)
    manifest_path = tmp_path / MANIFEST_FILENAME
    manifest = json.loads(manifest_path.read_text())

    if tamper == "model_version":
        manifest[tamper] = "other-model-version"
    elif tamper == "contract_version":
        manifest[tamper] = "window-inference-v1"
    elif tamper == "feature_schema":
        manifest[tamper] = "other-schema"
    elif tamper == "physical_rules_version":
        manifest[tamper] = "other-rules"
    elif tamper == "artifact_filename":
        manifest[tamper] = "other.joblib"
    elif tamper == "artifact_size_bytes":
        manifest[tamper] += 1
    elif tamper == "artifact_sha256":
        manifest[tamper] = "0" * 64
    elif tamper == "feature_columns":
        manifest[tamper] = ["other_feature"]
    elif tamper == "frozen_model":
        manifest[tamper]["minimum_physical_seconds"] = 4.0
    elif tamper == "provenance":
        manifest[tamper]["train_windows"] += 1
    else:
        manifest[tamper]["episodes"] += 1
    manifest_path.write_text(json.dumps(manifest))

    with pytest.raises(ValueError, match="manifest"):
        load_frozen_bundle(tmp_path / ARTIFACT_FILENAME, manifest_path)
