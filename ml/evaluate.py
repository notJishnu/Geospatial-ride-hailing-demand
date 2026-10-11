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


def eta_metrics(actual: pd.Series, predicted: pd.Series) -> dict[str, float]:
    """Return absolute duration metrics for ETA predictions measured in seconds."""
    actual_values = actual.to_numpy(dtype=float)
    predicted_values = np.maximum(predicted.to_numpy(dtype=float), 0.0)
    absolute_error = np.abs(predicted_values - actual_values)
    return {
        "mae_seconds": float(absolute_error.mean()),
        "mape": float((absolute_error / np.maximum(actual_values, 1.0)).mean()),
        "median_absolute_error_seconds": float(np.median(absolute_error)),
        "p90_absolute_error_seconds": float(np.quantile(absolute_error, 0.9)),
        "within_2_minutes": float((absolute_error <= 120).mean()),
        "within_5_minutes": float((absolute_error <= 300).mean()),
    }


def eta_slice_metrics(
    frame: pd.DataFrame, actual_column: str, predicted_column: str, by: str
) -> dict[str, dict[str, float]]:
    """Calculate ETA metrics independently for every non-empty reporting slice."""
    return {
        str(slice_value): eta_metrics(group[actual_column], group[predicted_column])
        for slice_value, group in frame.groupby(by, dropna=False)
    }
