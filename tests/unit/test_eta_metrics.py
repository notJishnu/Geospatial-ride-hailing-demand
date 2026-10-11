import pandas as pd

from ml.evaluate import eta_metrics


def test_eta_metrics_are_seconds_based_and_bounded() -> None:
    metrics = eta_metrics(pd.Series([60, 120, 300]), pd.Series([60, 180, -5]))
    assert metrics["mae_seconds"] == 120
    assert metrics["median_absolute_error_seconds"] == 60
    assert metrics["within_2_minutes"] == 2 / 3
    assert metrics["within_5_minutes"] == 1.0
