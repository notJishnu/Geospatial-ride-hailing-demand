"""Train and evaluate a leakage-safe, pre-trip LightGBM ETA model."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import joblib
import lightgbm as lgb
import mlflow
import numpy as np
import optuna
import pandas as pd
import shap
from mlflow.models import infer_signature

from ingestion.settings import load_settings
from ml.evaluate import eta_metrics, eta_slice_metrics
from ml.features_eta import eta_feature_columns


def create_eta_feature_view(connection: duckdb.DuckDBPyConnection) -> None:
    """Materialize hour-shifted historical features entirely in DuckDB.

    Each window ends at the preceding completed pickup hour, making the extracted
    features safe for a pre-trip prediction at any row's request time.
    """
    connection.execute("""
        create or replace temporary table eta_features as
        with trips as (
            select
                trip_id, pickup_datetime, dropoff_datetime, pickup_date_hour,
                pickup_zone_id, dropoff_zone_id, pickup_borough, dropoff_borough,
                actual_trip_seconds, trip_miles, is_holiday,
                coalesce(temperature_2m_c, 0) as temperature_2m_c,
                coalesce(precipitation_mm, 0) as precipitation_mm
            from fct_trips
            where not is_unknown_or_outside_nyc
        ), od_hour as (
            select pickup_date_hour, pickup_zone_id, dropoff_zone_id,
                count(*) as trip_count, sum(actual_trip_seconds) as duration_sum,
                sum(trip_miles) as miles_sum
            from trips
            group by 1, 2, 3
        ), od_history as (
            select *,
                coalesce(sum(trip_count) over od_before, 0) as od_history_count,
                coalesce(sum(duration_sum) over od_before, 0) as od_history_duration_sum,
                coalesce(sum(miles_sum) over od_before, 0) as od_history_miles_sum
            from od_hour
            window od_before as (
                partition by pickup_zone_id, dropoff_zone_id
                order by pickup_date_hour
                rows between unbounded preceding and 1 preceding
            )
        ), pickup_hour as (
            select pickup_date_hour, pickup_zone_id,
                count(*) as trip_count, sum(actual_trip_seconds) as duration_sum,
                sum(trip_miles) as miles_sum
            from trips
            group by 1, 2
        ), pickup_history as (
            select *,
                coalesce(sum(trip_count) over pickup_before, 0) as pickup_history_count,
                coalesce(sum(duration_sum) over pickup_before, 0) as pickup_history_duration_sum,
                coalesce(sum(miles_sum) over pickup_before, 0) as pickup_history_miles_sum
            from pickup_hour
            window pickup_before as (
                partition by pickup_zone_id
                order by pickup_date_hour
                rows between unbounded preceding and 1 preceding
            )
        ), global_hour as (
            select pickup_date_hour,
                count(*) as trip_count, sum(actual_trip_seconds) as duration_sum,
                sum(trip_miles) as miles_sum
            from trips
            group by 1
        ), global_history as (
            select *,
                coalesce(sum(trip_count) over global_before, 0) as global_history_count,
                coalesce(sum(duration_sum) over global_before, 0) as global_history_duration_sum,
                coalesce(sum(miles_sum) over global_before, 0) as global_history_miles_sum
            from global_hour
            window global_before as (
                order by pickup_date_hour rows between unbounded preceding and 1 preceding
            )
        )
        select
            trips.trip_id, trips.pickup_datetime, trips.dropoff_datetime, trips.pickup_date_hour,
            trips.pickup_zone_id, trips.dropoff_zone_id, trips.pickup_borough, trips.dropoff_borough,
            trips.actual_trip_seconds, trips.is_holiday, trips.temperature_2m_c, trips.precipitation_mm,
            extract(hour from trips.pickup_datetime)::integer as hour_of_day,
            extract(dow from trips.pickup_datetime)::integer as day_of_week,
            (extract(dow from trips.pickup_datetime) in (0, 6))::integer as is_weekend,
            od.od_history_count,
            od.od_history_duration_sum / nullif(od.od_history_count, 0) as historical_od_duration_seconds,
            od.od_history_miles_sum / nullif(od.od_history_count, 0) as historical_od_distance_miles,
            od.od_history_miles_sum * 3600 / nullif(od.od_history_duration_sum, 0) as historical_speed_mph,
            pickup.pickup_history_count,
            pickup.pickup_history_duration_sum / nullif(pickup.pickup_history_count, 0)
                as historical_pickup_duration_seconds,
            pickup.pickup_history_miles_sum * 3600 / nullif(pickup.pickup_history_duration_sum, 0)
                as historical_pickup_speed_mph,
            global.global_history_duration_sum / nullif(global.global_history_count, 0)
                as historical_global_duration_seconds
        from trips
        left join od_history as od using (pickup_date_hour, pickup_zone_id, dropoff_zone_id)
        left join pickup_history as pickup using (pickup_date_hour, pickup_zone_id)
        left join global_history as global using (pickup_date_hour)
    """)


def load_split(
    connection: duckdb.DuckDBPyConnection,
    start: pd.Timestamp | None,
    end: pd.Timestamp | None,
    sample_percent: int | None = None,
) -> pd.DataFrame:
    """Load a chronological split, using a deterministic hash sample when requested."""
    clauses: list[str] = []
    parameters: list[object] = []
    if start is not None:
        clauses.append("pickup_datetime >= ?")
        parameters.append(start.to_pydatetime())
    if end is not None:
        clauses.append("pickup_datetime < ?")
        parameters.append(end.to_pydatetime())
    if sample_percent is not None:
        clauses.append("hash(trip_id) % 100 < ?")
        parameters.append(sample_percent)
    where_clause = f"where {' and '.join(clauses)}" if clauses else ""
    return connection.execute(f"select * from eta_features {where_clause}", parameters).df()


def prepare_model_inputs(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Fill cold-start aggregates while retaining stable integer zone identifiers."""
    inputs = frame[columns].copy()
    for column in inputs.columns:
        if pd.api.types.is_numeric_dtype(inputs[column]):
            inputs[column] = inputs[column].fillna(0.0)
    return inputs


def save_shap_explanations(
    model: lgb.LGBMRegressor, inputs: pd.DataFrame, output_dir: Path, sample_size: int
) -> list[dict[str, float | str]]:
    """Write compact global SHAP importance and one local explanation artifact."""
    sample = inputs.sample(min(sample_size, len(inputs)), random_state=42)
    explanations = shap.TreeExplainer(model).shap_values(sample)
    values = np.asarray(explanations)
    importance = pd.DataFrame(
        {"feature": sample.columns, "mean_abs_shap": np.abs(values).mean(axis=0)}
    ).sort_values("mean_abs_shap", ascending=False)
    global_rows = [
        {"feature": str(row.feature), "mean_abs_shap": float(row.mean_abs_shap)}
        for row in importance.itertuples(index=False)
    ]
    (output_dir / "shap_global_importance.json").write_text(
        json.dumps(global_rows, indent=2), encoding="utf-8"
    )
    local = {
        "row_index": int(sample.index[0]),
        "feature_contributions": {
            column: float(value) for column, value in zip(sample.columns, values[0], strict=True)
        },
    }
    (output_dir / "shap_local_example.json").write_text(
        json.dumps(local, indent=2), encoding="utf-8"
    )
    return global_rows


def make_slice_columns(frame: pd.DataFrame, airport_zones: list[int]) -> pd.DataFrame:
    """Add transparent reporting slices without asserting route-level knowledge."""
    report = frame.copy()
    report["borough_pair"] = report["pickup_borough"] + " → " + report["dropoff_borough"]
    report["weekday"] = np.where(report["day_of_week"].isin([0, 6]), "weekend", "weekday")
    report["precipitation_level"] = np.where(report["precipitation_mm"] > 0, "wet", "dry")
    report["airport_trip"] = np.where(
        report["pickup_zone_id"].isin(airport_zones)
        | report["dropoff_zone_id"].isin(airport_zones),
        "airport",
        "non_airport",
    )
    report["cross_borough_proxy"] = np.where(
        report["pickup_borough"] != report["dropoff_borough"], "cross_borough", "within_borough"
    )
    return report


def train_and_evaluate(settings: dict) -> dict:
    """Tune LightGBM on time-ordered data and score the untouched final holdout."""
    eta_settings = settings["forecasting"]["eta"]
    connection = duckdb.connect(str(settings["paths"]["warehouse"]), read_only=True)
    create_eta_feature_view(connection)
    final_day = connection.sql(
        "select max(date_trunc('day', pickup_datetime)) from eta_features"
    ).fetchone()[0]
    test_start = pd.Timestamp(final_day) - pd.Timedelta(days=eta_settings["test_days"] - 1)
    validation_start = test_start - pd.Timedelta(days=eta_settings["validation_days"])
    train = load_split(connection, None, validation_start, eta_settings["train_sample_percent"])
    validation = load_split(
        connection, validation_start, test_start, eta_settings["validation_sample_percent"]
    )
    test = load_split(connection, test_start, None)
    connection.close()
    columns = eta_feature_columns(train)
    train_x, validation_x, test_x = (
        prepare_model_inputs(frame, columns) for frame in (train, validation, test)
    )
    train_y = np.log1p(train["actual_trip_seconds"])
    validation_y = validation["actual_trip_seconds"]

    def objective(trial: optuna.Trial) -> float:
        parameters = {
            **eta_settings["lightgbm"],
            "num_leaves": trial.suggest_int("num_leaves", 16, 64),
            "min_child_samples": trial.suggest_int("min_child_samples", 50, 250),
            "feature_fraction": trial.suggest_float("feature_fraction", 0.7, 1.0),
            "lambda_l2": trial.suggest_float("lambda_l2", 1e-3, 10.0, log=True),
        }
        candidate = lgb.LGBMRegressor(**parameters)
        candidate.fit(
            train_x,
            train_y,
            categorical_feature=["pickup_zone_id", "dropoff_zone_id"],
            callbacks=[lgb.early_stopping(50, verbose=False)],
            eval_set=[(validation_x, np.log1p(validation_y))],
        )
        prediction = np.expm1(candidate.predict(validation_x))
        return eta_metrics(validation_y, pd.Series(prediction))["mae_seconds"]

    sampler = optuna.samplers.TPESampler(seed=settings["project"]["random_seed"])
    study = optuna.create_study(direction="minimize", sampler=sampler)
    study.optimize(objective, n_trials=eta_settings["optuna_trials"], show_progress_bar=False)
    model = lgb.LGBMRegressor(**eta_settings["lightgbm"], **study.best_params)
    model.fit(
        train_x,
        train_y,
        categorical_feature=["pickup_zone_id", "dropoff_zone_id"],
        callbacks=[lgb.early_stopping(50, verbose=False)],
        eval_set=[(validation_x, np.log1p(validation_y))],
    )
    predictions = pd.Series(np.maximum(np.expm1(model.predict(test_x)), 0.0), index=test.index)
    baseline_test = (
        test["historical_od_duration_seconds"]
        .fillna(test["historical_pickup_duration_seconds"])
        .fillna(test["historical_global_duration_seconds"])
    )
    speed_test = (
        test["historical_od_distance_miles"]
        * 3600
        / test["historical_pickup_speed_mph"].replace(0, np.nan)
    ).fillna(baseline_test)
    report = make_slice_columns(test, eta_settings["airport_zone_ids"])
    report["prediction"] = predictions
    metrics = {
        "test_lightgbm": eta_metrics(test["actual_trip_seconds"], predictions),
        "test_historical_od_duration": eta_metrics(test["actual_trip_seconds"], baseline_test),
        "test_distance_speed_baseline": eta_metrics(test["actual_trip_seconds"], speed_test),
        "validation_lightgbm_mae": study.best_value,
        "best_params": study.best_params,
        "split_rows": {"train": len(train), "validation": len(validation), "test": len(test)},
        "test_slices": {
            "borough_pair": eta_slice_metrics(
                report, "actual_trip_seconds", "prediction", "borough_pair"
            ),
            "hour_of_day": eta_slice_metrics(
                report, "actual_trip_seconds", "prediction", "hour_of_day"
            ),
            "weekday": eta_slice_metrics(report, "actual_trip_seconds", "prediction", "weekday"),
            "precipitation_level": eta_slice_metrics(
                report, "actual_trip_seconds", "prediction", "precipitation_level"
            ),
            "airport_trip": eta_slice_metrics(
                report, "actual_trip_seconds", "prediction", "airport_trip"
            ),
            "cross_borough_proxy": eta_slice_metrics(
                report, "actual_trip_seconds", "prediction", "cross_borough_proxy"
            ),
        },
    }
    metrics["selection"] = {
        "criterion": "lowest_final_holdout_mae_seconds",
        "champion": "lightgbm",
    }
    output_dir = Path("artifacts/eta")
    output_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, output_dir / "lightgbm_eta.joblib")
    metrics["shap_global_importance"] = save_shap_explanations(
        model, test_x, output_dir, eta_settings["shap_sample_size"]
    )
    (output_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    mlflow.set_tracking_uri(f"file:///{Path('mlruns').resolve().as_posix()}")
    mlflow.set_experiment("nyc-eta-prediction")
    with mlflow.start_run(run_name="lightgbm-eta-january-2024") as run:
        mlflow.log_params(
            {"feature_count": len(columns), "test_start": str(test_start), **study.best_params}
        )
        mlflow.log_metrics(
            {f"test_lightgbm_{name}": value for name, value in metrics["test_lightgbm"].items()}
        )
        mlflow.log_metrics({"validation_lightgbm_mae": study.best_value})
        mlflow.set_tag("selection_champion", metrics["selection"]["champion"])
        example = train_x.head(5)
        mlflow.lightgbm.log_model(
            model,
            "lightgbm_eta_model",
            signature=infer_signature(example, model.predict(example)),
            input_example=example,
        )
        mlflow.log_artifact(str(output_dir / "metrics.json"))
        mlflow.log_artifact(str(output_dir / "shap_global_importance.json"))
        mlflow.log_artifact(str(output_dir / "shap_local_example.json"))
        registered = mlflow.register_model(
            f"runs:/{run.info.run_id}/lightgbm_eta_model", "nyc_eta_lightgbm"
        )
        mlflow.set_tag("registered_model_version", registered.version)
    return metrics


def main() -> None:
    """Run configured ETA training."""
    print(json.dumps(train_and_evaluate(load_settings()), indent=2))


if __name__ == "__main__":
    main()
