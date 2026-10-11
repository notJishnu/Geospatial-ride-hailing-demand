"""Monthly, idempotent Dagster assets for the NYC mobility warehouse."""

from __future__ import annotations

import subprocess
import sys
from datetime import date
from pathlib import Path

from dagster import (
    AssetKey,
    AssetSelection,
    Backoff,
    Failure,
    MetadataValue,
    MonthlyPartitionsDefinition,
    RetryPolicy,
    RunFailureSensorContext,
    asset,
    run_failure_sensor,
)

from ingestion.build_calendar import build_calendar
from ingestion.download_reference import download_reference_data
from ingestion.download_tlc import download_month as download_tlc_month
from ingestion.download_weather import download_month as download_weather_month
from ingestion.settings import load_settings

MONTHLY_PARTITIONS = MonthlyPartitionsDefinition(
    start_date="2024-01-01", timezone="America/New_York", end_offset=0
)
NETWORK_RETRY_POLICY = RetryPolicy(max_retries=3, delay=30, backoff=Backoff.EXPONENTIAL)
DBT_RETRY_POLICY = RetryPolicy(max_retries=2, delay=60, backoff=Backoff.EXPONENTIAL)


def month_from_partition_key(partition_key: str) -> str:
    """Convert Dagster's monthly date key to the project's YYYY-MM source key."""
    return date.fromisoformat(partition_key).strftime("%Y-%m")


@run_failure_sensor(name="local_failure_alert")
def local_failure_alert(context: RunFailureSensorContext) -> None:
    """Emit local failure details without inventing an external alert channel."""
    context.log.error(
        "Pipeline failure alert: job=%s run_id=%s. Inspect Dagster event logs before retrying.",
        context.dagster_run.job_name,
        context.dagster_run.run_id,
    )


@asset(
    key=AssetKey("reference_data"),
    group_name="ingestion",
    retry_policy=NETWORK_RETRY_POLICY,
)
def reference_data(context) -> None:  # type: ignore[no-untyped-def]
    """Download immutable TLC zone references and rebuild the configured date calendar."""
    settings = load_settings()
    download_reference_data(settings)
    calendar = build_calendar(settings)
    destination = Path(settings["paths"]["reference"]) / "calendar" / "calendar_dates.parquet"
    destination.parent.mkdir(parents=True, exist_ok=True)
    calendar.write_parquet(destination)
    context.add_output_metadata({"calendar_rows": len(calendar), "calendar_path": str(destination)})


@asset(
    key=AssetKey("bronze_hvfhv"),
    partitions_def=MONTHLY_PARTITIONS,
    group_name="ingestion",
    retry_policy=NETWORK_RETRY_POLICY,
)
def bronze_hvfhv(context) -> None:  # type: ignore[no-untyped-def]
    """Materialize one immutable monthly HVFHV Bronze partition idempotently."""
    month = month_from_partition_key(context.partition_key)
    manifest = download_tlc_month(month, load_settings())
    context.add_output_metadata(
        {
            "month": month,
            "result": "downloaded" if manifest is not None else "already_present",
        }
    )


@asset(
    key=AssetKey("weather_hourly"),
    partitions_def=MONTHLY_PARTITIONS,
    group_name="ingestion",
    retry_policy=NETWORK_RETRY_POLICY,
)
def weather_hourly(context) -> None:  # type: ignore[no-untyped-def]
    """Materialize one normalized hourly-weather partition idempotently."""
    month = month_from_partition_key(context.partition_key)
    manifest = download_weather_month(month, load_settings())
    context.add_output_metadata(
        {
            "month": month,
            "result": "downloaded" if manifest is not None else "already_present",
        }
    )


@asset(
    key=AssetKey("warehouse_models"),
    partitions_def=MONTHLY_PARTITIONS,
    deps=[AssetKey("reference_data"), AssetKey("bronze_hvfhv"), AssetKey("weather_hourly")],
    group_name="warehouse",
    retry_policy=DBT_RETRY_POLICY,
)
def warehouse_models(context) -> None:  # type: ignore[no-untyped-def]
    """Build and test Silver/Gold models for one month through dbt's incremental logic."""
    month = month_from_partition_key(context.partition_key)
    result = subprocess.run(
        [
            str(Path(sys.executable).parent / "Scripts" / "dbt.exe"),
            "build",
            "--project-dir",
            "dbt_project",
            "--profiles-dir",
            "dbt_project",
            "--vars",
            f"{{target_month: {month}}}",
        ],
        check=False,
        text=True,
    )
    if result.returncode != 0:
        raise Failure(f"dbt build failed for {month} with exit code {result.returncode}")
    context.add_output_metadata(
        {"month": month, "dbt_command": MetadataValue.text("dbt build with target_month")}
    )


monthly_refresh_selection = AssetSelection.assets(warehouse_models)
