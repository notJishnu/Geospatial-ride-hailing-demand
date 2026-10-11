"""Run one Dagster monthly partition from the command line for local backfill checks."""

from __future__ import annotations

import argparse

from orchestration.dagster_project.definitions import defs


def main() -> None:
    """Execute the complete monthly-refresh asset job and fail the process on errors."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--partition", required=True, help="Dagster monthly key, e.g. 2024-01-01")
    args = parser.parse_args()
    result = defs.get_job_def("monthly_refresh_job").execute_in_process(
        partition_key=args.partition, raise_on_error=False
    )
    if not result.success:
        raise SystemExit(f"Dagster monthly_refresh_job failed for {args.partition}")


if __name__ == "__main__":
    main()
