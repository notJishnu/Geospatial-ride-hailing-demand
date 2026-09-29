"""Train and evaluate a leakage-safe global LightGBM demand model."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import joblib
import lightgbm as lgb
import mlflow
import pandas as pd

from ingestion.settings import load_settings
from ml.evaluate import demand_metrics
from ml.features import build_demand_features, demand_feature_columns


def load_demand_frame(database_path: Path) -> pd.DataFrame:
    """Create a complete known-zone/hour panel from Gold demand and date dimensions."""
    connection = duckdb.connect(str(database_path), read_only=True)
    query = """
        with zones as (
            select zone_id, borough from dim_zone where not is_unknown_or_outside_nyc
        ), hours as (
            select date_hour, is_holiday, precipitation_mm, temperature_2m_c
            from dim_date_hour
        )
        select
            zones.zone_id,
            zones.borough,
            hours.date_hour,
            coalesce(demand.trip_count, 0) as trip_count,
            hours.is_holiday::integer as is_holiday,
            coalesce(hours.precipitation_mm, 0) as precipitation_mm,
            hours.temperature_2m_c
        from zones cross join hours
        left join agg_zone_hour_demand as demand
            on zones.zone_id = demand.zone_id and hours.date_hour = demand.date_hour
        order by zones.zone_id, hours.date_hour
    """
    frame = connection.sql(query).df()
    connection.close()
    frame["date_hour"] = pd.to_datetime(frame["date_hour"])
    frame["is_holiday"] = frame["is_holiday"].fillna(0).astype(int)
    return frame


def seasonal_naive_predictions(frame: pd.DataFrame, lag_hours: int = 168) -> pd.Series:
    """Return same-zone, same-hour-last-week baseline predictions."""
    return frame.groupby("zone_id", sort=False)["trip_count"].shift(lag_hours).fillna(0.0)


def train_and_evaluate(settings: dict) -> dict:
    """Train chronological model and log a reproducible local MLflow run."""
    demand_settings = settings["forecasting"]["demand"]
    frame = load_demand_frame(Path(settings["paths"]["warehouse"]))
    featured = build_demand_features(
        frame,
        lags=demand_settings["lag_hours"],
        rolling_windows=demand_settings["rolling_windows_hours"],
    )
    max_lag = max(max(demand_settings["lag_hours"]), max(demand_settings["rolling_windows_hours"]))
    featured = featured.groupby("zone_id", group_keys=False).apply(lambda rows: rows.iloc[max_lag:])
    featured = featured.reset_index(drop=True)
    final_hour = featured["date_hour"].max()
    test_start = final_hour - pd.Timedelta(days=demand_settings["test_days"] - 1)
    validation_start = test_start - pd.Timedelta(days=demand_settings["validation_days"])
    train = featured.loc[featured["date_hour"] < validation_start].copy()
    validation = featured.loc[
        (featured["date_hour"] >= validation_start) & (featured["date_hour"] < test_start)
    ].copy()
    test = featured.loc[featured["date_hour"] >= test_start].copy()
    feature_columns = demand_feature_columns(featured)
    model = lgb.LGBMRegressor(**demand_settings["lightgbm"])
    model.fit(train[feature_columns], train["trip_count"])
    validation_predictions = pd.Series(
        model.predict(validation[feature_columns]), index=validation.index
    )
    test_predictions = pd.Series(model.predict(test[feature_columns]), index=test.index)
    test_baseline = seasonal_naive_predictions(featured).loc[test.index]
    metrics = {
        "validation_lightgbm": demand_metrics(validation["trip_count"], validation_predictions),
        "test_lightgbm": demand_metrics(test["trip_count"], test_predictions),
        "test_seasonal_naive": demand_metrics(test["trip_count"], test_baseline),
    }
    output_dir = Path("artifacts/demand")
    output_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, output_dir / "lightgbm_demand.joblib")
    (output_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    mlflow.set_tracking_uri(f"file:///{Path('mlruns').resolve().as_posix()}")
    mlflow.set_experiment("nyc-demand-forecasting")
    with mlflow.start_run(run_name="lightgbm-demand-january-2024"):
        mlflow.log_params(
            {
                "feature_count": len(feature_columns),
                "test_start": str(test_start),
                **demand_settings["lightgbm"],
            }
        )
        mlflow.log_metrics(
            {f"test_lightgbm_{name}": value for name, value in metrics["test_lightgbm"].items()}
        )
        mlflow.log_metrics(
            {
                f"test_seasonal_naive_{name}": value
                for name, value in metrics["test_seasonal_naive"].items()
            }
        )
        mlflow.log_artifact(str(output_dir / "metrics.json"))
    return metrics


def main() -> None:
    """Train the configured local demand model."""
    print(json.dumps(train_and_evaluate(load_settings()), indent=2))


if __name__ == "__main__":
    main()
