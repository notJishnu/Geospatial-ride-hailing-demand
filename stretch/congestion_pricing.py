"""Descriptive comparison of completed NYC months around a pricing policy window."""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb
import pandas as pd

from ingestion.settings import load_settings
from monitoring.drift_report import validate_month


def monthly_fee_summary(warehouse: Path, month: str) -> pd.DataFrame:
    """Summarize observed trip outcomes for one completed month, without causal claims."""
    connection = duckdb.connect(str(warehouse), read_only=True)
    try:
        return connection.execute(
            """
            select
                ingestion_month,
                count(*) as trip_count,
                avg(actual_trip_seconds) as average_trip_seconds,
                avg(trip_miles) as average_trip_miles,
                avg(coalesce(congestion_surcharge, 0)) as average_congestion_surcharge,
                sum(coalesce(congestion_surcharge, 0)) as congestion_surcharge_total
            from fct_trips
            where ingestion_month = ?
            group by ingestion_month
            """,
            [validate_month(month)],
        ).df()
    finally:
        connection.close()


def compare_months(warehouse: Path, pre_month: str, post_month: str) -> pd.DataFrame:
    """Return a transparent before/after table; it is not a causal estimator."""
    pre = monthly_fee_summary(warehouse, pre_month).assign(period="pre")
    post = monthly_fee_summary(warehouse, post_month).assign(period="post")
    comparison = pd.concat([pre, post], ignore_index=True)
    if comparison.empty:
        raise ValueError("One or both requested months are not available in fct_trips")
    return comparison


def main() -> None:
    """Print a completed-month comparison selected explicitly by the operator."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--pre-month", required=True)
    parser.add_argument("--post-month", required=True)
    args = parser.parse_args()
    settings = load_settings()
    result = compare_months(Path(settings["paths"]["warehouse"]), args.pre_month, args.post_month)
    print(result.to_string(index=False))
    print("Descriptive comparison only: no causal effect is identified by this output.")


if __name__ == "__main__":
    main()
