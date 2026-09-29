"""Metrics and slices for time-aware demand forecasts."""

from __future__ import annotations

import numpy as np
import pandas as pd


def demand_metrics(actual: pd.Series, predicted: pd.Series) -> dict[str, float]:
    """Return MAE, RMSE, WAPE, and signed bias for non-negative demand predictions."""
    actual_values = actual.to_numpy(dtype=float)
    predicted_values = np.maximum(predicted.to_numpy(dtype=float), 0.0)
    errors = predicted_values - actual_values
    denominator = np.abs(actual_values).sum()
    return {
        "mae": float(np.abs(errors).mean()),
        "rmse": float(np.sqrt(np.mean(errors**2))),
        "wape": float(np.abs(errors).sum() / denominator) if denominator else 0.0,
        "bias": float(errors.sum() / denominator) if denominator else 0.0,
    }


def demand_slice_metrics(
    frame: pd.DataFrame, actual_column: str, predicted_column: str, by: str
) -> dict[str, dict[str, float]]:
    """Calculate demand metrics independently for every non-empty reporting slice."""
    return {
        str(slice_value): demand_metrics(group[actual_column], group[predicted_column])
        for slice_value, group in frame.groupby(by, dropna=False)
    }
