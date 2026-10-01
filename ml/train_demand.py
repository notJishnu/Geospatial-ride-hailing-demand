"""Train and evaluate a leakage-safe global LightGBM demand model."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import joblib
import lightgbm as lgb
import mlflow
import pandas as pd
from mlflow.models import infer_signature
from statsforecast import StatsForecast
from statsforecast.models import AutoETS

from ingestion.settings import load_settings
from ml.evaluate import demand_metrics, demand_slice_metrics
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


def moving_average_predictions(frame: pd.DataFrame, window_hours: int = 24) -> pd.Series:
    """Return a trailing zone-level moving-average benchmark."""
    return (
        frame.groupby("zone_id", sort=False)["trip_count"]
        .transform(lambda values: values.shift(1).rolling(window_hours, min_periods=1).mean())
        .fillna(0.0)
    )


def statsforecast_top_zone_metrics(
    frame: pd.DataFrame, test: pd.DataFrame, top_n: int
) -> dict[str, float]:
    """Evaluate a chronological AutoETS benchmark on the highest-volume zones."""
    top_zones = (
        frame.groupby("zone_id", as_index=False)["trip_count"]
        .sum()
        .nlargest(top_n, "trip_count")["zone_id"]
        .tolist()
    )
    cutoff = test["date_hour"].min()
    training = frame.loc[(frame["zone_id"].isin(top_zones)) & (frame["date_hour"] < cutoff)].copy()
    evaluation = test.loc[test["zone_id"].isin(top_zones)].copy()
    sf_input = training.rename(
        columns={"zone_id": "unique_id", "date_hour": "ds", "trip_count": "y"}
    )[["unique_id", "ds", "y"]]
    forecast = StatsForecast(models=[AutoETS(season_length=24)], freq="h", n_jobs=1).forecast(
        df=sf_input, h=evaluation["date_hour"].nunique()
    )
    merged = evaluation.merge(
        forecast.rename(columns={"unique_id": "zone_id", "ds": "date_hour"}),
        on=["zone_id", "date_hour"],
        how="inner",
        validate="one_to_one",
    )
    return demand_metrics(merged["trip_count"], merged["AutoETS"])


def rolling_origin_metrics(
    featured: pd.DataFrame,
    feature_columns: list[str],
    model_settings: dict,
    *,
    first_test_start: pd.Timestamp,
    test_days: int,
    folds: int,
) -> list[dict[str, object]]:
    """Refit and evaluate chronological expanding-window folds before final test selection."""
    outcomes: list[dict[str, object]] = []
    for fold_index in range(folds):
        start = first_test_start - pd.Timedelta(days=test_days * (folds - fold_index - 1))
        end = start + pd.Timedelta(days=test_days)
        training = featured.loc[featured["date_hour"] < start]
        evaluation = featured.loc[
            (featured["date_hour"] >= start) & (featured["date_hour"] < end)
        ].copy()
        if training.empty or evaluation.empty:
            continue
        model = lgb.LGBMRegressor(**model_settings)
        model.fit(training[feature_columns], training["trip_count"])
        predictions = pd.Series(model.predict(evaluation[feature_columns]), index=evaluation.index)
        outcomes.append(
            {
                "fold": fold_index + 1,
                "test_start": str(start),
                "lightgbm": demand_metrics(evaluation["trip_count"], predictions),
                "seasonal_naive": demand_metrics(
                    evaluation["trip_count"],
                    seasonal_naive_predictions(featured).loc[evaluation.index],
                ),
                "moving_average": demand_metrics(
                    evaluation["trip_count"],
                    moving_average_predictions(featured).loc[evaluation.index],
                ),
            }
        )
    return outcomes


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
    featured = featured.groupby("zone_id", group_keys=False).tail(-max_lag).reset_index(drop=True)
    final_hour = featured["date_hour"].max()
    test_start = final_hour - pd.Timedelta(days=demand_settings["test_days"] - 1)
    validation_start = test_start - pd.Timedelta(days=demand_settings["validation_days"])
    train = featured.loc[featured["date_hour"] < validation_start].copy()
    validation = featured.loc[
        (featured["date_hour"] >= validation_start) & (featured["date_hour"] < test_start)
    ].copy()
    test = featured.loc[featured["date_hour"] >= test_start].copy()
    feature_columns = demand_feature_columns(featured)
    rolling_metrics = rolling_origin_metrics(
        featured,
        feature_columns,
        demand_settings["lightgbm"],
        first_test_start=validation_start,
        test_days=demand_settings["test_days"],
        folds=demand_settings["rolling_origin_folds"],
    )
    model = lgb.LGBMRegressor(**demand_settings["lightgbm"])
    model.fit(train[feature_columns], train["trip_count"])
    validation_predictions = pd.Series(
        model.predict(validation[feature_columns]), index=validation.index
    )
    test_predictions = pd.Series(model.predict(test[feature_columns]), index=test.index)
    test_baseline = seasonal_naive_predictions(featured).loc[test.index]
    test_moving_average = moving_average_predictions(featured).loc[test.index]
    test_report = test.copy()
    test_report["prediction"] = test_predictions
    test_report["weather_slice"] = (
        test_report["precipitation_mm"].gt(0).map({True: "wet", False: "dry"})
    )
    zone_volume = train.groupby("zone_id")["trip_count"].sum()
    test_report["zone_volume_tier"] = pd.qcut(
        test_report["zone_id"].map(zone_volume),
        q=3,
        labels=["low", "medium", "high"],
        duplicates="drop",
    ).astype(str)
    metrics = {
        "validation_lightgbm": demand_metrics(validation["trip_count"], validation_predictions),
        "test_lightgbm": demand_metrics(test["trip_count"], test_predictions),
        "test_seasonal_naive": demand_metrics(test["trip_count"], test_baseline),
        "test_moving_average": demand_metrics(test["trip_count"], test_moving_average),
        "test_autoets_top_zones": statsforecast_top_zone_metrics(
            frame, test, demand_settings["statsforecast_top_zones"]
        ),
        "rolling_origin": rolling_metrics,
        "test_slices": {
            "hour_of_day": demand_slice_metrics(
                test_report, "trip_count", "prediction", "hour_of_day"
            ),
            "weather": demand_slice_metrics(
                test_report, "trip_count", "prediction", "weather_slice"
            ),
            "zone_volume_tier": demand_slice_metrics(
                test_report, "trip_count", "prediction", "zone_volume_tier"
            ),
        },
    }
    test_wape = {
        "lightgbm": metrics["test_lightgbm"]["wape"],
        "seasonal_naive": metrics["test_seasonal_naive"]["wape"],
        "moving_average": metrics["test_moving_average"]["wape"],
    }
    metrics["selection"] = {
        "criterion": "lowest_final_holdout_wape",
        "champion": min(test_wape, key=test_wape.get),
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
                f"test_autoets_top_zones_{name}": value
                for name, value in metrics["test_autoets_top_zones"].items()
            }
        )
        mlflow.log_metrics(
            {
                f"test_seasonal_naive_{name}": value
                for name, value in metrics["test_seasonal_naive"].items()
            }
        )
        mlflow.log_metrics(
            {
                f"test_moving_average_{name}": value
                for name, value in metrics["test_moving_average"].items()
            }
        )
        mlflow.set_tag("selection_champion", metrics["selection"]["champion"])
        example = train[feature_columns].head(5)
        mlflow.lightgbm.log_model(
            model,
            "lightgbm_demand_model",
            signature=infer_signature(example, model.predict(example)),
            input_example=example,
        )
        mlflow.log_artifact(str(output_dir / "metrics.json"))
    return metrics


def main() -> None:
    """Train the configured local demand model."""
    print(json.dumps(train_and_evaluate(load_settings()), indent=2))


if __name__ == "__main__":
    main()
