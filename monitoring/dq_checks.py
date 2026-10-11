"""Warehouse-level quality checks and local alert artifacts."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb

from ingestion.settings import load_settings


def quality_status(
    reject_rate: float, duplicate_trip_ids: int, max_reject_rate: float
) -> list[str]:
    """Return human-readable quality alerts for configured hard thresholds."""
    alerts: list[str] = []
    if reject_rate > max_reject_rate:
        alerts.append(
            f"reject rate {reject_rate:.2%} exceeds configured threshold {max_reject_rate:.2%}"
        )
    if duplicate_trip_ids:
        alerts.append(f"fct_trips contains {duplicate_trip_ids:,} duplicate trip IDs")
    return alerts


def eta_mae_alert(
    current_mae: float, baseline_mae: float, max_increase_fraction: float
) -> str | None:
    """Alert when the latest recorded ETA MAE regresses past its configured tolerance."""
    if current_mae > baseline_mae * (1 + max_increase_fraction):
        return (
            f"ETA MAE {current_mae:.1f}s exceeds baseline {baseline_mae:.1f}s "
            f"by more than {max_increase_fraction:.0%}"
        )
    return None


def run_checks(settings: dict[str, Any]) -> dict[str, Any]:
    """Check Gold completeness and Silver quarantine volume without mutating the warehouse."""
    warehouse = Path(settings["paths"]["warehouse"])
    if not warehouse.exists():
        raise FileNotFoundError(f"Warehouse not found: {warehouse}")
    connection = duckdb.connect(str(warehouse), read_only=True)
    try:
        facts = connection.execute(
            """
            select
                count(*) as valid_rows,
                count(*) - count(distinct trip_id) as duplicate_trip_ids,
                count(*) filter (where pickup_datetime is null or dropoff_datetime is null) as null_timestamps,
                count(*) filter (where actual_trip_seconds not between 60 and 21600) as invalid_duration_rows
            from fct_trips
            """
        ).fetchone()
        quarantine_rows = connection.execute(
            "select count(*) from silver_trips_quarantine"
        ).fetchone()[0]
    finally:
        connection.close()
    valid_rows, duplicate_trip_ids, null_timestamps, invalid_duration_rows = map(int, facts)
    total_rows = valid_rows + quarantine_rows
    reject_rate = quarantine_rows / total_rows if total_rows else 0.0
    alerts = quality_status(
        reject_rate,
        duplicate_trip_ids,
        settings["monitoring"]["thresholds"]["max_reject_rate"],
    )
    if null_timestamps:
        alerts.append(f"fct_trips has {null_timestamps:,} null pickup/dropoff timestamps")
    if invalid_duration_rows:
        alerts.append(
            f"fct_trips has {invalid_duration_rows:,} rows outside configured duration bounds"
        )
    eta_metrics_path = Path("artifacts/eta/metrics.json")
    eta_mae: float | None = None
    if eta_metrics_path.exists():
        eta_metrics = json.loads(eta_metrics_path.read_text(encoding="utf-8"))
        eta_mae = float(eta_metrics["test_lightgbm"]["mae_seconds"])
        eta_alert = eta_mae_alert(
            eta_mae,
            settings["monitoring"]["thresholds"]["eta_baseline_mae_seconds"],
            settings["monitoring"]["thresholds"]["max_eta_mae_increase_fraction"],
        )
        if eta_alert:
            alerts.append(eta_alert)
    return {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "status": "alert" if alerts else "pass",
        "metrics": {
            "valid_rows": valid_rows,
            "quarantine_rows": quarantine_rows,
            "reject_rate": reject_rate,
            "duplicate_trip_ids": duplicate_trip_ids,
            "null_timestamps": null_timestamps,
            "invalid_duration_rows": invalid_duration_rows,
            "eta_mae_seconds": eta_mae,
        },
        "alerts": alerts,
    }


def main() -> None:
    """Write the most recent data-quality result to an ignored local artifact."""
    settings = load_settings()
    report = run_checks(settings)
    output = Path(settings["monitoring"]["output_dir"]) / "dq_report.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if report["status"] == "alert":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
