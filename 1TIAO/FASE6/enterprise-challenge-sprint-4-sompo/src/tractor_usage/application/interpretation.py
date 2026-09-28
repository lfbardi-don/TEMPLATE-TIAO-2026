"""Versioned reading aids layered on top of frozen model outputs.

Nothing here changes a model decision. Regime kinds were assigned once by
reading the fitted K-Means centers in physical units; exposure bands only
bucket the existing relative exposure score.
"""

from __future__ import annotations

from tractor_usage.application.contracts import ExposureBand, RegimeLabel


REGIME_LABELS_VERSION = "regime-labels-v1"
EXPOSURE_BANDS_VERSION = "exposure-bands-v1"

_REGIME_KINDS = {
    "fendt314-hybrid-v2.0.1": (
        RegimeLabel(id=0, kind="field_hitch_work"),
        RegimeLabel(id=1, kind="field_pto_variable"),
        RegimeLabel(id=2, kind="road_transport"),
    ),
}

_TYPICAL_LOWER = 25.0
_TYPICAL_UPPER = 75.0


def regime_labels(model_version: str) -> tuple[RegimeLabel, ...]:
    return _REGIME_KINDS.get(model_version, ())


def exposure_band(relative_exposure_score: float | None) -> ExposureBand | None:
    if relative_exposure_score is None:
        return None
    if relative_exposure_score < _TYPICAL_LOWER:
        return "BELOW_TYPICAL"
    if relative_exposure_score < _TYPICAL_UPPER:
        return "TYPICAL"
    return "ABOVE_TYPICAL"
