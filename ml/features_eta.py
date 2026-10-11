"""Point-in-time-safe feature helpers for pre-trip ETA prediction."""

from __future__ import annotations

import numpy as np
import pandas as pd


def build_point_in_time_eta_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Add prior-hour OD, pickup-zone, and global aggregates without using actual trip miles.

    Aggregates are formed at the hour level, then shifted one complete hour before
    being joined back. Consequently, no trip can read its own duration, distance,
    or another observation from the prediction hour.
    """
    required = {
        "pickup_datetime",
        "pickup_zone_id",
        "dropoff_zone_id",
        "actual_trip_seconds",
        "trip_miles",
    }
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"ETA frame is missing required columns: {sorted(missing)}")

    result = frame.copy()
    result["pickup_datetime"] = pd.to_datetime(result["pickup_datetime"])
    result["pickup_date_hour"] = result["pickup_datetime"].dt.floor("h")
    result = result.sort_values("pickup_datetime").reset_index(drop=True)

    hourly_od = (
        result.groupby(["pickup_date_hour", "pickup_zone_id", "dropoff_zone_id"], as_index=False)
        .agg(
            od_trip_count=("actual_trip_seconds", "size"),
            od_duration_sum=("actual_trip_seconds", "sum"),
            od_miles_sum=("trip_miles", "sum"),
        )
        .sort_values(["pickup_zone_id", "dropoff_zone_id", "pickup_date_hour"])
    )
    od_group = hourly_od.groupby(["pickup_zone_id", "dropoff_zone_id"], sort=False)
    hourly_od["od_history_count"] = od_group["od_trip_count"].cumsum() - hourly_od["od_trip_count"]
    hourly_od["od_history_duration_sum"] = (
        od_group["od_duration_sum"].cumsum() - hourly_od["od_duration_sum"]
    )
    hourly_od["od_history_miles_sum"] = (
        od_group["od_miles_sum"].cumsum() - hourly_od["od_miles_sum"]
    )

    hourly_pickup = (
        result.groupby(["pickup_date_hour", "pickup_zone_id"], as_index=False)
        .agg(
            pickup_trip_count=("actual_trip_seconds", "size"),
            pickup_duration_sum=("actual_trip_seconds", "sum"),
            pickup_miles_sum=("trip_miles", "sum"),
        )
        .sort_values(["pickup_zone_id", "pickup_date_hour"])
    )
    pickup_group = hourly_pickup.groupby("pickup_zone_id", sort=False)
    hourly_pickup["pickup_history_count"] = (
        pickup_group["pickup_trip_count"].cumsum() - hourly_pickup["pickup_trip_count"]
    )
    hourly_pickup["pickup_history_duration_sum"] = (
        pickup_group["pickup_duration_sum"].cumsum() - hourly_pickup["pickup_duration_sum"]
    )
    hourly_pickup["pickup_history_miles_sum"] = (
        pickup_group["pickup_miles_sum"].cumsum() - hourly_pickup["pickup_miles_sum"]
    )

    hourly_global = (
        result.groupby("pickup_date_hour", as_index=False)
        .agg(
            global_trip_count=("actual_trip_seconds", "size"),
            global_duration_sum=("actual_trip_seconds", "sum"),
            global_miles_sum=("trip_miles", "sum"),
        )
        .sort_values("pickup_date_hour")
    )
    for column in ("global_trip_count", "global_duration_sum", "global_miles_sum"):
        hourly_global[f"global_history_{column.removeprefix('global_')}"] = (
            hourly_global[column].cumsum() - hourly_global[column]
        )

    result = (
        result.merge(
            hourly_od[
                [
                    "pickup_date_hour",
                    "pickup_zone_id",
                    "dropoff_zone_id",
                    "od_history_count",
                    "od_history_duration_sum",
                    "od_history_miles_sum",
                ]
            ],
            on=["pickup_date_hour", "pickup_zone_id", "dropoff_zone_id"],
            how="left",
            validate="many_to_one",
        )
        .merge(
            hourly_pickup[
                [
                    "pickup_date_hour",
                    "pickup_zone_id",
                    "pickup_history_count",
                    "pickup_history_duration_sum",
                    "pickup_history_miles_sum",
                ]
            ],
            on=["pickup_date_hour", "pickup_zone_id"],
            how="left",
            validate="many_to_one",
        )
        .merge(
            hourly_global[
                [
                    "pickup_date_hour",
                    "global_history_trip_count",
                    "global_history_duration_sum",
                    "global_history_miles_sum",
                ]
            ],
            on="pickup_date_hour",
            how="left",
            validate="many_to_one",
        )
    )
    result["historical_od_duration_seconds"] = result["od_history_duration_sum"] / result[
        "od_history_count"
    ].replace(0, np.nan)
    result["historical_od_distance_miles"] = result["od_history_miles_sum"] / result[
        "od_history_count"
    ].replace(0, np.nan)
    result["historical_pickup_duration_seconds"] = result["pickup_history_duration_sum"] / result[
        "pickup_history_count"
    ].replace(0, np.nan)
    result["historical_global_duration_seconds"] = result["global_history_duration_sum"] / result[
        "global_history_trip_count"
    ].replace(0, np.nan)
    result["historical_speed_mph"] = (
        result["od_history_miles_sum"] * 3600 / result["od_history_duration_sum"].replace(0, np.nan)
    )
    result["hour_of_day"] = result["pickup_datetime"].dt.hour
    result["day_of_week"] = result["pickup_datetime"].dt.dayofweek
    result["is_weekend"] = (result["day_of_week"] >= 5).astype(int)
    return result


def eta_feature_columns(frame: pd.DataFrame) -> list[str]:
    """Return serving-safe ETA inputs, explicitly excluding outcome-only fields."""
    excluded = {
        "trip_id",
        "pickup_datetime",
        "dropoff_datetime",
        "pickup_date_hour",
        "actual_trip_seconds",
        "reported_trip_seconds",
        "trip_miles",
        "average_speed_mph",
        "wait_seconds",
        "driver_arrival_delay_seconds",
        "base_passenger_fare",
        "tolls",
        "bcf",
        "sales_tax",
        "congestion_surcharge",
        "airport_fee",
        "tips",
        "driver_pay",
        "platform_take_approx",
        "driver_pay_per_mile",
        "driver_pay_per_minute",
    }
    return [
        column
        for column in frame.columns
        if column not in excluded and frame[column].dtype != "object"
    ]
