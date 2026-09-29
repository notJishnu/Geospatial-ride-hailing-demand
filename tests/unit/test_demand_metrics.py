import pandas as pd

from ml.evaluate import demand_slice_metrics


def test_demand_slice_metrics_returns_each_slice() -> None:
    frame = pd.DataFrame({"slice": ["dry", "wet"], "actual": [10, 20], "predicted": [9, 22]})
    metrics = demand_slice_metrics(frame, "actual", "predicted", "slice")
    assert set(metrics) == {"dry", "wet"}
    assert metrics["dry"]["mae"] == 1.0
