"""Create an Evidently feature-drift report for two completed ingestion months."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from ingestion.settings import load_settings

MONTH_PATTERN = re.compile(r"^\d{4}-\d{2}$")
DRIFT_COLUMNS = [
    "trip_miles",
    "actual_trip_seconds",
    "average_speed_mph",
    "base_passenger_fare",
    "driver_pay",
    "wait_seconds",
    "precipitation_mm",
]


def validate_month(value: str) -> str:
    """Validate a month string before using it as a parameterized query value."""
    if not MONTH_PATTERN.fullmatch(value):
        raise ValueError(f"Expected month in YYYY-MM format, got {value!r}")
    return value


def load_month_sample(
    connection: duckdb.DuckDBPyConnection, month: str, sample_size: int
) -> pd.DataFrame:
    """Read a deterministic trip sample for a configured completed month."""
    return connection.execute(
        f"""
        select {", ".join(DRIFT_COLUMNS)}
        from fct_trips
        where ingestion_month = ? and not is_unknown_or_outside_nyc
        order by hash(trip_id)
        limit ?
        """,
        [validate_month(month), sample_size],
    ).df()


def drift_status(reference_month: str | None, current_month: str | None) -> str:
    """Describe whether two different configured months are available for comparison."""
    if not reference_month or not current_month:
        return "waiting_for_comparison_month"
    if reference_month == current_month:
        return "waiting_for_distinct_comparison_month"
    return "ready"


def find_drift_share(value: Any) -> float | None:
    """Extract Evidently's aggregate drift share across compatible report layouts."""
    if isinstance(value, dict):
        if "share_of_drifted_columns" in value:
            return float(value["share_of_drifted_columns"])
        for nested in value.values():
            found = find_drift_share(nested)
            if found is not None:
                return found
    if isinstance(value, list):
        for nested in value:
            found = find_drift_share(nested)
            if found is not None:
                return found
    return None


def run_drift_report(settings: dict[str, Any]) -> dict[str, Any]:
    """Generate HTML/JSON Evidently artifacts when a valid month pair is configured."""
    drift_settings = settings["monitoring"]["drift"]
    reference_month = drift_settings.get("reference_month")
    current_month = drift_settings.get("current_month")
    status = drift_status(reference_month, current_month)
    result: dict[str, Any] = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "status": status,
        "reference_month": reference_month,
        "current_month": current_month,
    }
    if status != "ready":
        return result
    try:
        from evidently.metric_preset import DataDriftPreset
        from evidently.report import Report
    except ImportError as error:
        raise RuntimeError(
            "Evidently is required for drift reports. Install the project's monitoring extra first."
        ) from error

    connection = duckdb.connect(str(settings["paths"]["warehouse"]), read_only=True)
    try:
        reference = load_month_sample(connection, reference_month, drift_settings["sample_size"])
        current = load_month_sample(connection, current_month, drift_settings["sample_size"])
    finally:
        connection.close()
    if reference.empty or current.empty:
        return {**result, "status": "waiting_for_nonempty_months"}
    report = Report(metrics=[DataDriftPreset()])
    report.run(reference_data=reference, current_data=current)
    output_dir = Path(settings["monitoring"]["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    html_path = output_dir / f"drift_{reference_month}_to_{current_month}.html"
    report.save_html(str(html_path))
    report_json = report.as_dict()
    json_path = html_path.with_suffix(".json")
    json_path.write_text(json.dumps(report_json, indent=2), encoding="utf-8")
    drift_share = find_drift_share(report_json)
    max_share = drift_settings["max_drifted_columns_share"]
    is_alert = drift_share is not None and drift_share > max_share
    return {
        **result,
        "status": "alert" if is_alert else "generated",
        "reference_rows": len(reference),
        "current_rows": len(current),
        "html_report": str(html_path),
        "json_report": str(json_path),
        "drifted_columns_share": drift_share,
        "max_drifted_columns_share": max_share,
    }


def main() -> None:
    """Run drift monitoring and write a concise status file for the dashboard/runbook."""
    settings = load_settings()
    result = run_drift_report(settings)
    output = Path(settings["monitoring"]["output_dir"]) / "drift_status.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
