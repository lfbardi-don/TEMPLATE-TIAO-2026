"""Operational-regime candidate evaluation with frozen validation gates."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from itertools import combinations
from typing import Literal

import numpy as np
import pandas as pd
from sklearn.base import ClusterMixin
from sklearn.cluster import KMeans
from sklearn.impute import SimpleImputer
from sklearn.metrics import adjusted_rand_score, silhouette_score
from sklearn.mixture import GaussianMixture
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import RobustScaler


ModelKind = Literal["kmeans", "gaussian_mixture"]


@dataclass(frozen=True)
class RegimeCandidateMetrics:
    kind: ModelKind
    components: int
    silhouette: float
    stability_ari: float
    minimum_train_fraction: float
    minimum_validation_fraction: float
    minimum_interpretable_features: int
    passes_gate: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class RegimeModel:
    kind: ModelKind
    components: int
    feature_columns: tuple[str, ...]
    preprocessor: Pipeline
    estimator: ClusterMixin | GaussianMixture
    regime_reasons: dict[int, tuple[str, ...]]

    def transform(self, frame: pd.DataFrame) -> np.ndarray:
        return self.preprocessor.transform(frame.loc[:, self.feature_columns])

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        return self.estimator.predict(self.transform(frame)).astype(int)


@dataclass
class RegimeSelection:
    candidates: tuple[RegimeCandidateMetrics, ...]
    selected_metrics: RegimeCandidateMetrics | None
    model: RegimeModel | None

    @property
    def accepted(self) -> bool:
        return self.selected_metrics is not None and self.selected_metrics.passes_gate

    def report(self) -> dict[str, object]:
        return {
            "accepted": self.accepted,
            "selected": self.selected_metrics.to_dict()
            if self.selected_metrics is not None
            else None,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
        }


def _estimator(kind: ModelKind, components: int, seed: int):
    if kind == "kmeans":
        return KMeans(
            n_clusters=components,
            n_init=20,
            random_state=seed,
        )
    return GaussianMixture(
        n_components=components,
        covariance_type="diag",
        n_init=1,
        reg_covar=1e-5,
        random_state=seed,
    )


def _trainable_columns(
    train: pd.DataFrame, requested: tuple[str, ...]
) -> tuple[str, ...]:
    selected = tuple(
        column
        for column in requested
        if train[column].notna().any() and train[column].nunique(dropna=True) > 1
    )
    if not selected:
        raise ValueError("all requested model features are empty or constant in train")
    return selected


def _minimum_fraction(labels: np.ndarray, components: int) -> float:
    counts = np.bincount(labels, minlength=components)
    return float(counts.min() / len(labels))


def _centers(estimator) -> np.ndarray:
    if isinstance(estimator, KMeans):
        return estimator.cluster_centers_
    return estimator.means_


def _regime_reasons(
    estimator, feature_columns: tuple[str, ...], minimum_deviation: float = 0.5
) -> dict[int, tuple[str, ...]]:
    reasons: dict[int, tuple[str, ...]] = {}
    for regime, center in enumerate(_centers(estimator)):
        ranked = np.argsort(np.abs(center))[::-1]
        deviating = tuple(
            feature_columns[index]
            for index in ranked
            if abs(float(center[index])) >= minimum_deviation
        )
        # A central regime is still meaningful: it represents typical operation.
        # Keep its three closest-to-defining dimensions available for explanation.
        fallback = tuple(feature_columns[index] for index in ranked[:3])
        reasons[regime] = tuple(dict.fromkeys((*deviating, *fallback)))
    return reasons


def _stability(predictions: list[np.ndarray]) -> float:
    scores = [
        adjusted_rand_score(left, right)
        for left, right in combinations(predictions, 2)
    ]
    return float(np.mean(scores)) if scores else 1.0


def evaluate_regime_candidates(
    train: pd.DataFrame,
    validation: pd.DataFrame,
    feature_columns: tuple[str, ...],
    *,
    component_range: range = range(3, 9),
    seeds: tuple[int, ...] = (0, 1, 2, 3, 4),
) -> RegimeSelection:
    """Fit only train, score only validation, and select against frozen gates."""

    usable = _trainable_columns(train, feature_columns)
    preprocessor = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", RobustScaler()),
        ]
    )
    x_train = preprocessor.fit_transform(train.loc[:, usable])
    x_validation = preprocessor.transform(validation.loc[:, usable])

    metrics: list[RegimeCandidateMetrics] = []
    fitted: dict[tuple[ModelKind, int], object] = {}
    reasons_by_candidate: dict[tuple[ModelKind, int], dict[int, tuple[str, ...]]] = {}

    for kind in ("kmeans", "gaussian_mixture"):
        for components in component_range:
            predictions: list[np.ndarray] = []
            primary = None
            train_labels = None
            for seed in seeds:
                candidate = _estimator(kind, components, seed)
                candidate.fit(x_train)
                predictions.append(candidate.predict(x_validation).astype(int))
                if seed == seeds[0]:
                    primary = candidate
                    train_labels = candidate.predict(x_train).astype(int)

            assert primary is not None and train_labels is not None
            validation_labels = predictions[0]
            unique_validation = np.unique(validation_labels)
            silhouette = (
                float(
                    silhouette_score(
                        x_validation,
                        validation_labels,
                        sample_size=min(2000, len(validation_labels)),
                        random_state=0,
                    )
                )
                if len(unique_validation) >= 2
                else -1.0
            )
            reasons = _regime_reasons(primary, usable)
            minimum_interpretable = min(map(len, reasons.values()), default=0)
            value = RegimeCandidateMetrics(
                kind=kind,
                components=components,
                silhouette=silhouette,
                stability_ari=_stability(predictions),
                minimum_train_fraction=_minimum_fraction(train_labels, components),
                minimum_validation_fraction=_minimum_fraction(
                    validation_labels, components
                ),
                minimum_interpretable_features=minimum_interpretable,
                passes_gate=bool(
                    silhouette >= 0.20
                    and _stability(predictions) >= 0.75
                    and _minimum_fraction(train_labels, components) >= 0.01
                    and minimum_interpretable >= 3
                ),
            )
            metrics.append(value)
            fitted[(kind, components)] = primary
            reasons_by_candidate[(kind, components)] = reasons

    accepted = [candidate for candidate in metrics if candidate.passes_gate]
    selected = max(
        accepted,
        key=lambda value: (value.stability_ari, value.silhouette),
        default=None,
    )
    if selected is None:
        return RegimeSelection(tuple(metrics), None, None)

    key = (selected.kind, selected.components)
    return RegimeSelection(
        candidates=tuple(metrics),
        selected_metrics=selected,
        model=RegimeModel(
            kind=selected.kind,
            components=selected.components,
            feature_columns=usable,
            preprocessor=preprocessor,
            estimator=fitted[key],
            regime_reasons=reasons_by_candidate[key],
        ),
    )
