"""Run the frozen V2 selection path without opening test by default."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from tractor_usage.experiments.selection import run_selection
from tractor_usage.modeling.hybrid import (
    HybridUsageModel,
    audit_scored_hybrid,
)
from tractor_usage.modeling.longitudinal import (
    aggregate_integrity_horizons,
    fit_longitudinal_baseline,
)
def _authorized_test_report(
    frame: pd.DataFrame, model: HybridUsageModel
) -> dict[str, object]:
    test = frame.loc[frame["split"].eq("test")].copy()
    if test.empty:
        raise ValueError("test authorization was supplied but test rows are absent")
    test = test.sort_values("observed_at_utc", kind="stable")
    scored = model.score(test)
    observed_hours = float(scored["sample_count"].sum() / 3600.0)
    metrics = audit_scored_hybrid(test, scored, model)

    train = frame.loc[frame["split"].eq("train")].copy()
    train = train.sort_values("observed_at_utc", kind="stable")
    baseline = fit_longitudinal_baseline(model.score(train))
    history = frame.sort_values("observed_at_utc", kind="stable")
    scored_history = model.score(history)
    as_of = pd.to_datetime(test["observed_at_utc"], utc=True).max()
    return {
        "status": "OPENED_BY_EXPLICIT_FLAG",
        "scored": True,
        "frozen_model": {
            "regime_kind": model.regime_model.kind,
            "regime_components": model.regime_model.components,
            "rarity_kind": model.kind,
            "threshold_quantile": model.threshold_quantile,
        },
        "windows": len(scored),
        "observed_hours": observed_hours,
        "metrics": metrics.to_dict(),
        "final_decision": "GO" if metrics.passes_gate else "NO-GO",
        "longitudinal": [
            score.to_dict()
            for score in aggregate_integrity_horizons(
                scored_history,
                as_of,
                baseline,
            )
        ],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--windows", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument(
        "--authorize-test",
        action="store_true",
        help="open the held-out test only after a separate explicit decision",
    )
    return parser


def main() -> None:
    args = _parser().parse_args()
    frame = pd.read_csv(args.windows)
    frame["observed_at_utc"] = pd.to_datetime(
        frame["observed_at_utc"], format="mixed", utc=True
    )
    frame = frame.sort_values("observed_at_utc", kind="stable").reset_index(drop=True)
    report, model = run_selection(frame)
    if args.authorize_test:
        if model is None:
            raise RuntimeError("test cannot open because validation did not pass")
        report["test"] = _authorized_test_report(frame, model)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True))
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
