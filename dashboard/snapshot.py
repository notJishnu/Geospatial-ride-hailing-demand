"""Build a compact, deployable dashboard snapshot from local Gold marts."""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb

TABLE_QUERIES = {
    # The dashboard shows all-month OD flows, not hour-level records. Aggregating
    # here keeps the hosted snapshot small enough for a practical app download.
    "agg_od_matrix": """
        select
            pickup_zone_id,
            dropoff_zone_id,
            sum(trip_count) as trip_count,
            avg(average_trip_seconds) as average_trip_seconds
        from source_warehouse.agg_od_matrix
        group by pickup_zone_id, dropoff_zone_id
    """,
    "agg_zone_hour_demand": "select * from source_warehouse.agg_zone_hour_demand",
    "dim_zone": "select * from source_warehouse.dim_zone",
    "kpi_driver_economics": "select * from source_warehouse.kpi_driver_economics",
    "kpi_zone_daily": "select * from source_warehouse.kpi_zone_daily",
    "silver_trips_quarantine": "select * from source_warehouse.silver_trips_quarantine",
}


def build_snapshot(source: Path, destination: Path, artifact_paths: dict[str, Path]) -> None:
    """Copy dashboard-sized marts and metric JSON without copying immutable Bronze data.

    Existing destinations are rejected to prevent accidental replacement. The snapshot
    intentionally excludes the large trip fact table and any raw TLC records.
    """
    if not source.exists():
        raise FileNotFoundError(f"Source warehouse not found: {source}")
    if destination.exists():
        raise FileExistsError(f"Snapshot already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_literal = str(source.resolve()).replace("'", "''")
    connection = duckdb.connect(str(destination))
    try:
        connection.execute(f"attach '{source_literal}' as source_warehouse (read_only)")
        for table_name, source_query in TABLE_QUERIES.items():
            connection.execute(f"create table {table_name} as {source_query}")
        connection.execute(
            """
            create table dashboard_health as
            select
                (select count(*) from source_warehouse.fct_trips) as gold_trip_count,
                (select count(*) from source_warehouse.silver_trips_quarantine) as quarantine_row_count
            """
        )
        connection.execute(
            "create table dashboard_artifacts (artifact_name varchar, contents varchar)"
        )
        for name, path in artifact_paths.items():
            if path.exists():
                connection.execute(
                    "insert into dashboard_artifacts values (?, ?)",
                    [name, path.read_text(encoding="utf-8")],
                )
    finally:
        connection.close()


def main() -> None:
    """Create the Git-ignored dashboard snapshot used for Streamlit deployment."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("data/warehouse/nyc_mobility.duckdb"))
    parser.add_argument(
        "--output", type=Path, default=Path("data/dashboard/nyc_dashboard_snapshot.duckdb")
    )
    args = parser.parse_args()
    build_snapshot(
        args.source,
        args.output,
        {
            "demand_metrics": Path("artifacts/demand/metrics.json"),
            "eta_metrics": Path("artifacts/eta/metrics.json"),
            "dq_report": Path("artifacts/monitoring/dq_report.json"),
            "drift_report": Path("artifacts/monitoring/drift_status.json"),
        },
    )
    print(f"Created deployable dashboard snapshot at {args.output}")


if __name__ == "__main__":
    main()
