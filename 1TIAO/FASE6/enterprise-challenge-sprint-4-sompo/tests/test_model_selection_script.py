import pandas as pd

from tractor_usage.experiments.selection import selection_splits


def test_selection_splits_never_returns_test_rows() -> None:
    frame = pd.DataFrame(
        {
            "split": ["train", "validation", "test"],
            "secret_test_value": [0, 0, 999],
        }
    )

    train, validation = selection_splits(frame)

    assert train["secret_test_value"].tolist() == [0]
    assert validation["secret_test_value"].tolist() == [0]
