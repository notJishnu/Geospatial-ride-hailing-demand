"""Dagster entry point: assets, monthly job, and safe-by-default schedule."""

from __future__ import annotations

from datetime import timedelta

from dagster import (
    DefaultScheduleStatus,
    Definitions,
    RunRequest,
    ScheduleDefinition,
    define_asset_job,
)

from orchestration.dagster_project.assets import (
    bronze_hvfhv,
    local_failure_alert,
    reference_data,
    warehouse_models,
    weather_hourly,
)

monthly_refresh_job = define_asset_job(
    "monthly_refresh_job",
    selection=[reference_data, bronze_hvfhv, weather_hourly, warehouse_models],
    description="Idempotently ingest, transform, and test one monthly HVFHV partition.",
)


def previous_month_partition_key(scheduled_time) -> str:  # type: ignore[no-untyped-def]
    """Return the prior calendar month as the expected Dagster partition key."""
    current_month = scheduled_time.date().replace(day=1)
    return (current_month - timedelta(days=1)).replace(day=1).isoformat()


def monthly_refresh_run_request(context) -> RunRequest:  # type: ignore[no-untyped-def]
    """Request the prior completed source month once TLC files are expected to exist."""
    return RunRequest(partition_key=previous_month_partition_key(context.scheduled_execution_time))


monthly_refresh_schedule = ScheduleDefinition(
    name="monthly_refresh_schedule",
    job=monthly_refresh_job,
    cron_schedule="0 8 5 * *",
    execution_timezone="America/New_York",
    execution_fn=monthly_refresh_run_request,
    default_status=DefaultScheduleStatus.STOPPED,
    description="Runs at 08:00 America/New_York on the fifth for the prior month.",
)

defs = Definitions(
    assets=[reference_data, bronze_hvfhv, weather_hourly, warehouse_models],
    jobs=[monthly_refresh_job],
    schedules=[monthly_refresh_schedule],
    sensors=[local_failure_alert],
)
