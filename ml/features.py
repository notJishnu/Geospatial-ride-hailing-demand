"""Point-in-time-safe feature builders for zone-hour demand forecasting."""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd


def build_demand_features(
    frame: pd.DataFrame,
    *,
    lags: Iterable[int],
    rolling_windows: Iterable[int],
) -> pd.DataFrame:
    """Build zone-hour features using only records strictly before each prediction hour.

    The input must contain one row per ``zone_id`` and ``date_hour`` with ``trip_count``.
    Lagged and rolling fields are grouped by zone and shifted before their calculation,
    preventing a row from reading its own target or any future target.
    """
    required = {"zone_id", "date_hour", "trip_count"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Demand frame is missing required columns: {sorted(missing)}")
    result = frame.sort_values(["zone_id", "date_hour"]).copy()
    grouped_target = result.groupby("zone_id", sort=False)["trip_count"]
    for lag in lags:
        result[f"lag_{lag}h"] = grouped_target.shift(lag)
    for window in rolling_windows:
        result[f"rolling_mean_{window}h"] = grouped_target.transform(
            lambda values, window=window: values.shift(1).rolling(window, min_periods=1).mean()
        )
    result["hour_of_day"] = result["date_hour"].dt.hour
    result["day_of_week"] = result["date_hour"].dt.dayofweek
    result["is_weekend"] = (result["day_of_week"] >= 5).astype(int)
    result["month"] = result["date_hour"].dt.month
    return result


def demand_feature_columns(frame: pd.DataFrame) -> list[str]:
    """Return model inputs, deliberately excluding the target and timestamp fields."""
    excluded = {
        "zone_id",
        "date_hour",
        "trip_count",
        "ingestion_month",
        "event_name",
        "holiday_name",
    }
    return [
        column
        for column in frame.columns
        if column not in excluded and frame[column].dtype != "object"
    ]
