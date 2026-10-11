"""Load the registered ETA model and build point-in-time-safe request features."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import expm1
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb
import holidays
import mlflow
import pandas as pd

FEATURE_COLUMNS = [
    "pickup_zone_id",
    "dropoff_zone_id",
    "is_holiday",
    "temperature_2m_c",
    "precipitation_mm",
    "hour_of_day",
    "day_of_week",
    "is_weekend",
    "od_history_count",
    "historical_od_duration_seconds",
    "historical_od_distance_miles",
    "historical_speed_mph",
    "pickup_history_count",
    "historical_pickup_duration_seconds",
    "historical_pickup_speed_mph",
    "historical_global_duration_seconds",
]


@dataclass(frozen=True)
class ModelSettings:
    """Local filesystem settings for a reproducible, laptop-only deployment."""

    warehouse_path: Path
    tracking_uri: str
    model_name: str = "nyc_eta_lightgbm"
    model_version: str = "1"
    timezone: str = "America/New_York"
    p90_absolute_error_seconds: float = 465.5222803222775


def default_settings() -> ModelSettings:
    """Build defaults relative to the repository root, with environment overrides."""
    import os

    root = Path(os.environ.get("NYC_MOBILITY_ROOT", Path.cwd()))
    tracking_dir = Path(os.environ.get("MLFLOW_TRACKING_DIR", root / "mlruns")).resolve()
    return ModelSettings(
        warehouse_path=Path(
            os.environ.get("WAREHOUSE_PATH", root / "data/warehouse/nyc_mobility.duckdb")
        ),
        tracking_uri=os.environ.get("MLFLOW_TRACKING_URI", tracking_dir.as_uri()),
        model_name=os.environ.get("ETA_MODEL_NAME", "nyc_eta_lightgbm"),
        model_version=os.environ.get("ETA_MODEL_VERSION", "1"),
    )


class EtaPredictor:
    """Registered model plus only the historical data allowed at request time."""

    def __init__(self, settings: ModelSettings) -> None:
        self.settings = settings
        mlflow.set_tracking_uri(settings.tracking_uri)
        self.model = mlflow.pyfunc.load_model(
            f"models:/{settings.model_name}/{settings.model_version}"
        )
        self.model_version = settings.model_version
        self.zone_ids = self._load_zone_ids()
        self._holidays = holidays.US(state="NY")

    def _connect(self) -> duckdb.DuckDBPyConnection:
        if not self.settings.warehouse_path.exists():
            raise FileNotFoundError(f"Warehouse not found: {self.settings.warehouse_path}")
        return duckdb.connect(str(self.settings.warehouse_path), read_only=True)

    def _load_zone_ids(self) -> set[int]:
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                select zone_id from dim_zone
                where not is_unknown_or_outside_nyc
                """
            ).fetchall()
        finally:
            connection.close()
        return {int(row[0]) for row in rows}

    def validate_zone_ids(self, pickup_zone_id: int, dropoff_zone_id: int) -> None:
        """Ensure both requested zones are known NYC zones used by the ETA training set."""
        invalid = {pickup_zone_id, dropoff_zone_id} - self.zone_ids
        if invalid:
            raise ValueError(f"Unknown or unsupported NYC zone IDs: {sorted(invalid)}")

    def build_features(
        self,
        pickup_zone_id: int,
        dropoff_zone_id: int,
        request_time: datetime,
        precipitation_mm: float | None,
    ) -> pd.DataFrame:
        """Return one model row using only completed hours before ``request_time``.

        The database query deliberately uses ``pickup_datetime < request_hour`` so
        trips in the in-progress prediction hour can never leak into its features.
        """
        self.validate_zone_ids(pickup_zone_id, dropoff_zone_id)
        local_time = request_time.astimezone(ZoneInfo(self.settings.timezone)).replace(tzinfo=None)
        request_hour = local_time.replace(minute=0, second=0, microsecond=0)
        connection = self._connect()
        try:
            historical = connection.execute(
                """
                with prior_trips as (
                    select * from fct_trips
                    where pickup_datetime < ? and not is_unknown_or_outside_nyc
                )
                select
                    count(*) filter (
                        where pickup_zone_id = ? and dropoff_zone_id = ?
                    ) as od_history_count,
                    avg(actual_trip_seconds) filter (
                        where pickup_zone_id = ? and dropoff_zone_id = ?
                    ) as historical_od_duration_seconds,
                    avg(trip_miles) filter (
                        where pickup_zone_id = ? and dropoff_zone_id = ?
                    ) as historical_od_distance_miles,
                    sum(trip_miles) filter (
                        where pickup_zone_id = ? and dropoff_zone_id = ?
                    ) * 3600 / nullif(sum(actual_trip_seconds) filter (
                        where pickup_zone_id = ? and dropoff_zone_id = ?
                    ), 0) as historical_speed_mph,
                    count(*) filter (where pickup_zone_id = ?) as pickup_history_count,
                    avg(actual_trip_seconds) filter (
                        where pickup_zone_id = ?
                    ) as historical_pickup_duration_seconds,
                    sum(trip_miles) filter (where pickup_zone_id = ?) * 3600
                        / nullif(sum(actual_trip_seconds) filter (where pickup_zone_id = ?), 0)
                        as historical_pickup_speed_mph,
                    avg(actual_trip_seconds) as historical_global_duration_seconds,
                    max(temperature_2m_c) filter (
                        where pickup_date_hour = ?
                    ) as temperature_2m_c,
                    max(precipitation_mm) filter (
                        where pickup_date_hour = ?
                    ) as observed_precipitation_mm
                from prior_trips
                """,
                [
                    request_hour,
                    pickup_zone_id,
                    dropoff_zone_id,
                    pickup_zone_id,
                    dropoff_zone_id,
                    pickup_zone_id,
                    dropoff_zone_id,
                    pickup_zone_id,
                    dropoff_zone_id,
                    pickup_zone_id,
                    dropoff_zone_id,
                    pickup_zone_id,
                    pickup_zone_id,
                    pickup_zone_id,
                    pickup_zone_id,
                    request_hour,
                    request_hour,
                ],
            ).fetchone()
            column_names = [column[0] for column in connection.description]
        finally:
            connection.close()
        values = dict(zip(column_names, historical, strict=True))
        feature_values = {
            "pickup_zone_id": pickup_zone_id,
            "dropoff_zone_id": dropoff_zone_id,
            "is_holiday": local_time.date() in self._holidays,
            "temperature_2m_c": values["temperature_2m_c"] or 0.0,
            "precipitation_mm": (
                precipitation_mm
                if precipitation_mm is not None
                else values["observed_precipitation_mm"] or 0.0
            ),
            "hour_of_day": local_time.hour,
            "day_of_week": (local_time.weekday() + 1) % 7,
            "is_weekend": int(local_time.weekday() >= 5),
            **{
                column: values[column] or 0.0
                for column in (
                    "od_history_count",
                    "historical_od_duration_seconds",
                    "historical_od_distance_miles",
                    "historical_speed_mph",
                    "pickup_history_count",
                    "historical_pickup_duration_seconds",
                    "historical_pickup_speed_mph",
                    "historical_global_duration_seconds",
                )
            },
        }
        frame = pd.DataFrame([feature_values], columns=FEATURE_COLUMNS)
        integer_columns = [
            "pickup_zone_id",
            "dropoff_zone_id",
            "hour_of_day",
            "day_of_week",
            "is_weekend",
        ]
        frame[integer_columns] = frame[integer_columns].astype("int32")
        frame["is_holiday"] = frame["is_holiday"].astype(bool)
        return frame.astype(
            {
                column: "float64"
                for column in FEATURE_COLUMNS
                if column not in integer_columns + ["is_holiday"]
            }
        )

    def predict_minutes(self, features: pd.DataFrame) -> float:
        """Invert the training log1p target and return a non-negative ETA in minutes."""
        seconds = max(expm1(float(self.model.predict(features)[0])), 0.0)
        return seconds / 60.0

    def prediction_interval(self, eta_minutes: float) -> tuple[float, float]:
        """Return a symmetric empirical P90 absolute-error interval in minutes."""
        error_minutes = self.settings.p90_absolute_error_seconds / 60.0
        return max(0.0, eta_minutes - error_minutes), eta_minutes + error_minutes
