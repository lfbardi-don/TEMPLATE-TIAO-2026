import numpy as np
import pandas as pd

from tractor_usage.modeling.regimes import evaluate_regime_candidates


def test_regime_selection_fits_train_and_predicts_validation() -> None:
    rng = np.random.default_rng(7)
    train = pd.DataFrame(
        {
            "a": np.concatenate(
                [rng.normal(-4, 0.2, 100), rng.normal(0, 0.2, 100), rng.normal(4, 0.2, 100)]
            ),
            "b": np.concatenate(
                [rng.normal(-3, 0.2, 100), rng.normal(0, 0.2, 100), rng.normal(3, 0.2, 100)]
            ),
            "c": np.concatenate(
                [rng.normal(-2, 0.2, 100), rng.normal(0, 0.2, 100), rng.normal(2, 0.2, 100)]
            ),
        }
    )
    validation = train.sample(frac=0.5, random_state=3).reset_index(drop=True)

    result = evaluate_regime_candidates(
        train,
        validation,
        ("a", "b", "c"),
        component_range=range(3, 4),
        seeds=(0, 1),
    )

    assert result.accepted
    assert result.model is not None
    assert len(result.model.predict(validation)) == len(validation)
