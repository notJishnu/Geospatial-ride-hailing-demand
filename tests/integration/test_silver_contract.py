"""Integration assertions for an already-built Silver DuckDB warehouse."""

from pathlib import Path

import duckdb
import pytest


@pytest.mark.integration
def test_valid_and_quarantine_cover_configured_month() -> None:
    """Every classified January trip belongs to exactly one Silver output."""
    database = Path("data/warehouse/nyc_mobility.duckdb")
    if not database.exists():
        pytest.skip("Run dbt build before the Silver warehouse contract test")
    connection = duckdb.connect(str(database), read_only=True)
    valid_rows = connection.sql("select count(*) from main.silver_trips_valid").fetchone()[0]
    quarantine_rows = connection.sql(
        "select count(*) from main.silver_trips_quarantine"
    ).fetchone()[0]
    classified_rows = connection.sql(
        "select count(*) from main.silver_trips_classified"
    ).fetchone()[0]
    connection.close()
    assert valid_rows + quarantine_rows == classified_rows
