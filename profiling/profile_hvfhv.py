"""Profile one immutable TLC HVFHV Bronze partition with DuckDB."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb

from ingestion.download_tlc import parse_month
from ingestion.settings import load_settings


def _sql_path(path: Path) -> str:
    """Return a safely quoted, normalized local path for a DuckDB SQL literal."""
    return str(path.resolve()).replace("\\", "/").replace("'", "''")


def _scalar(connection: duckdb.DuckDBPyConnection, query: str) -> Any:
    """Return the first value of a single-value DuckDB query."""
    return connection.execute(query).fetchone()[0]


def profile_month(month: str, settings: dict[str, Any]) -> dict[str, Any]:
    """Return data-quality and distribution diagnostics for a downloaded Bronze month."""
    month = parse_month(month)
    year, month_number = month.split("-")
    bronze_path = (
        Path(settings["paths"]["bronze"])
        / "hvfhv"
        / f"year={year}"
        / f"month={month_number}"
        / f"fhvhv_tripdata_{month}.parquet"
    )
    lookup_path = Path(settings["paths"]["reference"]) / "sources" / "taxi_zone_lookup.csv"
    if not bronze_path.exists():
        raise FileNotFoundError(f"Bronze file is required before profiling: {bronze_path}")
    if not lookup_path.exists():
        raise FileNotFoundError(f"Zone lookup is required before profiling: {lookup_path}")

    connection = duckdb.connect()
    connection.execute("SET memory_limit = '8GB'")
    connection.execute(
        f"CREATE VIEW raw_hvfhv AS SELECT * FROM read_parquet('{_sql_path(bronze_path)}')"
    )
    connection.execute(
        f"CREATE VIEW zone_lookup AS SELECT * FROM read_csv_auto('{_sql_path(lookup_path)}', header = true)"
    )
    schema = connection.execute("DESCRIBE raw_hvfhv").fetchall()
    columns = [row[0] for row in schema]
    null_counts = {
        column: _scalar(connection, f'SELECT count(*) - count("{column}") FROM raw_hvfhv')
        for column in columns
    }
    base = """
        WITH derived AS (
            SELECT *, datediff('second', pickup_datetime, dropoff_datetime) AS actual_trip_seconds,
                trip_miles / NULLIF(trip_time / 3600.0, 0) AS average_speed_mph
            FROM raw_hvfhv
        )
    """
    quality = connection.execute(
        base
        + """
        SELECT count(*) AS row_count, min(request_datetime) AS min_request_datetime,
            max(request_datetime) AS max_request_datetime,
            sum(CASE WHEN dropoff_datetime <= pickup_datetime THEN 1 ELSE 0 END) AS nonpositive_duration_rows,
            sum(CASE WHEN actual_trip_seconds < 60 OR actual_trip_seconds > 21600 THEN 1 ELSE 0 END) AS duration_outside_start_thresholds,
            sum(CASE WHEN trip_miles <= 0 OR trip_miles >= 200 THEN 1 ELSE 0 END) AS miles_outside_start_thresholds,
            sum(CASE WHEN average_speed_mph >= 80 THEN 1 ELSE 0 END) AS speed_above_start_threshold,
            sum(CASE WHEN base_passenger_fare < 0 THEN 1 ELSE 0 END) AS negative_fare_rows,
            sum(CASE WHEN driver_pay < 0 THEN 1 ELSE 0 END) AS negative_driver_pay_rows,
            sum(CASE WHEN abs(actual_trip_seconds - trip_time) > 60 THEN 1 ELSE 0 END) AS trip_time_mismatch_over_60_seconds,
            quantile_cont(actual_trip_seconds, 0.01) AS duration_p01_seconds,
            quantile_cont(actual_trip_seconds, 0.50) AS duration_p50_seconds,
            quantile_cont(actual_trip_seconds, 0.99) AS duration_p99_seconds,
            quantile_cont(trip_miles, 0.01) AS miles_p01,
            quantile_cont(trip_miles, 0.50) AS miles_p50,
            quantile_cont(trip_miles, 0.99) AS miles_p99,
            quantile_cont(average_speed_mph, 0.99) AS speed_p99_mph
        FROM derived
        """
    ).fetchone()
    quality_columns = [item[0] for item in connection.description]
    quality_metrics = dict(zip(quality_columns, quality, strict=True))
    zone_metrics = connection.execute(
        """
        SELECT sum(CASE WHEN PULocationID NOT IN (SELECT LocationID FROM zone_lookup) THEN 1 ELSE 0 END) AS pickup_not_in_lookup,
            sum(CASE WHEN DOLocationID NOT IN (SELECT LocationID FROM zone_lookup) THEN 1 ELSE 0 END) AS dropoff_not_in_lookup,
            sum(CASE WHEN PULocationID IN (264, 265) THEN 1 ELSE 0 END) AS pickup_unknown_or_outside,
            sum(CASE WHEN DOLocationID IN (264, 265) THEN 1 ELSE 0 END) AS dropoff_unknown_or_outside
        FROM raw_hvfhv
        """
    ).fetchone()
    zone_columns = [item[0] for item in connection.description]
    duplicate_rows = _scalar(
        connection,
        """
        SELECT coalesce(sum(duplicate_count - 1), 0)
        FROM (SELECT count(*) AS duplicate_count FROM raw_hvfhv
              GROUP BY hvfhs_license_num, request_datetime, pickup_datetime, PULocationID, DOLocationID, base_passenger_fare)
        """,
    )
    top_zones = connection.execute(
        "SELECT PULocationID AS pickup_zone_id, count(*) AS trip_count FROM raw_hvfhv GROUP BY PULocationID ORDER BY trip_count DESC LIMIT 10"
    ).fetchall()
    connection.close()
    return {
        "month": month,
        "profiled_at_utc": datetime.now(UTC).isoformat(),
        "source_file": str(bronze_path),
        "schema": [{"name": name, "type": data_type} for name, data_type, *_ in schema],
        "null_counts": null_counts,
        "quality_metrics": quality_metrics,
        "zone_metrics": dict(zip(zone_columns, zone_metrics, strict=True)),
        "duplicate_rows": duplicate_rows,
        "top_pickup_zones": [
            {"pickup_zone_id": zone_id, "trip_count": count} for zone_id, count in top_zones
        ],
    }


def write_profile_report(profile: dict[str, Any], output: Path) -> None:
    """Write a transparent, evidence-backed Markdown profile report."""
    metrics = profile["quality_metrics"]
    rows = metrics["row_count"]

    def rate(value: int | float | None) -> str:
        return "n/a" if value is None else f"{value / rows:.4%}"

    schema_lines = "\n".join(
        f"| `{item['name']}` | `{item['type']}` |" for item in profile["schema"]
    )
    null_lines = "\n".join(
        f"| `{name}` | {count:,} | {rate(count)} |"
        for name, count in profile["null_counts"].items()
    )
    zone_lines = "\n".join(
        f"| {name} | {value:,} | {rate(value)} |" for name, value in profile["zone_metrics"].items()
    )
    top_zone_lines = "\n".join(
        f"| {item['pickup_zone_id']} | {item['trip_count']:,} |"
        for item in profile["top_pickup_zones"]
    )
    report = f"""# HVFHV Data Profile — {profile["month"]}

Generated {profile["profiled_at_utc"]} from immutable Bronze source `{profile["source_file"]}`. This is descriptive profiling, not causal analysis.

## Volume and time coverage

| Metric | Value |
|---|---:|
| Rows | {rows:,} |
| Earliest request | {metrics["min_request_datetime"]} |
| Latest request | {metrics["max_request_datetime"]} |
| Composite-key duplicate rows | {profile["duplicate_rows"]:,} ({rate(profile["duplicate_rows"])}) |

## Candidate cleaning-rule evidence

| Check | Rows | Rate |
|---|---:|---:|
| Non-positive duration | {metrics["nonpositive_duration_rows"]:,} | {rate(metrics["nonpositive_duration_rows"])} |
| Duration outside 60 sec–6 hr | {metrics["duration_outside_start_thresholds"]:,} | {rate(metrics["duration_outside_start_thresholds"])} |
| Miles outside (0, 200) | {metrics["miles_outside_start_thresholds"]:,} | {rate(metrics["miles_outside_start_thresholds"])} |
| Speed ≥80 mph | {metrics["speed_above_start_threshold"]:,} | {rate(metrics["speed_above_start_threshold"])} |
| Negative passenger fare | {metrics["negative_fare_rows"]:,} | {rate(metrics["negative_fare_rows"])} |
| Negative driver pay | {metrics["negative_driver_pay_rows"]:,} | {rate(metrics["negative_driver_pay_rows"])} |
| Actual vs reported duration differs by >60 sec | {metrics["trip_time_mismatch_over_60_seconds"]:,} | {rate(metrics["trip_time_mismatch_over_60_seconds"])} |

Observed percentiles: duration p01/p50/p99 = {metrics["duration_p01_seconds"]:.1f}/{metrics["duration_p50_seconds"]:.1f}/{metrics["duration_p99_seconds"]:.1f} seconds; miles p01/p50/p99 = {metrics["miles_p01"]:.2f}/{metrics["miles_p50"]:.2f}/{metrics["miles_p99"]:.2f}; speed p99 = {metrics["speed_p99_mph"]:.2f} mph.

Recommendation: retain the configured thresholds as initial Silver quarantine rules, not silent drops. Confirm final thresholds after more months and explicitly handle zone IDs 264/265 as unknown/outside-NYC categories.

## Zone checks

| Check | Rows | Rate |
|---|---:|---:|
{zone_lines}

## Ten busiest pickup zones

| Pickup zone ID | Trips |
|---:|---:|
{top_zone_lines}

## Schema

| Column | DuckDB type |
|---|---|
{schema_lines}

## Null counts

| Column | Null rows | Rate |
|---|---:|---:|
{null_lines}

## Limitations

TLC location fields are zone IDs, not GPS coordinates, and no driver or rider identities are present. These checks identify data-quality patterns only; they do not establish causes.
"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")


def main() -> None:
    """Profile the configured first month and save JSON plus Markdown artifacts."""
    settings = load_settings()
    profile = profile_month(settings["months"][0], settings)
    Path("data/profiles").mkdir(parents=True, exist_ok=True)
    Path("data/profiles/hvfhv_2024-01.json").write_text(
        json.dumps(profile, default=str, indent=2), encoding="utf-8"
    )
    write_profile_report(profile, Path("docs/data_profile.md"))


if __name__ == "__main__":
    main()
