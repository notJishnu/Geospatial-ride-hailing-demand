"""Tests for the portable Streamlit dashboard snapshot."""

from pathlib import Path

import duckdb
import pytest

from dashboard.snapshot import build_snapshot


def _create_source_warehouse(path: Path) -> None:
    connection = duckdb.connect(str(path))
    try:
        connection.execute(
            """
            create table agg_od_matrix as
            select * from (
                values (1, 2, 3::bigint, 120.0), (1, 2, 5::bigint, 180.0)
            ) as values_table(pickup_zone_id, dropoff_zone_id, trip_count, average_trip_seconds)
            """
        )
        for table_name in (
            "agg_zone_hour_demand",
            "dim_zone",
            "kpi_driver_economics",
            "kpi_zone_daily",
            "silver_trips_quarantine",
        ):
            connection.execute(f"create table {table_name} as select 1 as example_value")
        connection.execute("create table fct_trips as select * from range(2)")
    finally:
        connection.close()


def test_build_snapshot_uses_dashboard_marts_and_embeds_artifacts(tmp_path: Path) -> None:
    source = tmp_path / "source.duckdb"
    snapshot = tmp_path / "dashboard.duckdb"
    artifact = tmp_path / "metrics.json"
    artifact.write_text('{"mae": 1.2}', encoding="utf-8")
    _create_source_warehouse(source)

    build_snapshot(source, snapshot, {"eta_metrics": artifact})

    connection = duckdb.connect(str(snapshot), read_only=True)
    try:
        assert connection.execute("select trip_count from agg_od_matrix").fetchone() == (8,)
        assert connection.execute("select gold_trip_count from dashboard_health").fetchone() == (2,)
        assert connection.execute("select contents from dashboard_artifacts").fetchone() == (
            '{"mae": 1.2}',
        )
    finally:
        connection.close()


def test_build_snapshot_does_not_replace_an_existing_file(tmp_path: Path) -> None:
    source = tmp_path / "source.duckdb"
    snapshot = tmp_path / "dashboard.duckdb"
    _create_source_warehouse(source)
    build_snapshot(source, snapshot, {})

    with pytest.raises(FileExistsError):
        build_snapshot(source, snapshot, {})
