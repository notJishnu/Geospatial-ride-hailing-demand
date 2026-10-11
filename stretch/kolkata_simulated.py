"""Create a deterministic synthetic Kolkata delivery dataset for portability demos.

This module does not represent real Kolkata trips, demand, prices, drivers, or customers.
It exists solely to exercise the platform's tabular contracts without claiming a public
trip-data source that does not exist.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


def simulate_kolkata_deliveries(rows: int, seed: int = 42) -> pd.DataFrame:
    """Return deterministic, explicitly synthetic delivery-like records.

    Columns intentionally describe a generic origin/destination/time/distance contract
    rather than masquerading as TLC HVFHV data.
    """
    if rows <= 0:
        raise ValueError("rows must be positive")
    generator = np.random.default_rng(seed)
    request_time = pd.date_range("2024-01-01", periods=rows, freq="5min", tz="Asia/Kolkata")
    origin_zone = generator.integers(1, 31, size=rows)
    destination_zone = generator.integers(1, 31, size=rows)
    distance_km = generator.gamma(shape=2.0, scale=1.7, size=rows).clip(0.3, 25)
    peak_multiplier = np.where(request_time.hour.isin([8, 9, 18, 19, 20]), 1.35, 1.0)
    duration_minutes = (distance_km * 4.2 * peak_multiplier + generator.normal(8, 2, rows)).clip(
        5, 180
    )
    return pd.DataFrame(
        {
            "simulation_id": [f"kolkata-sim-{index:07d}" for index in range(rows)],
            "request_datetime": request_time,
            "origin_zone_id": origin_zone,
            "destination_zone_id": destination_zone,
            "synthetic_distance_km": distance_km.round(3),
            "synthetic_duration_seconds": (duration_minutes * 60).round().astype("int64"),
            "is_simulated": True,
            "simulation_seed": seed,
        }
    )


def main() -> None:
    """Write a local, Git-ignored synthetic portability fixture."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--output", type=Path, default=Path("data/simulated/kolkata_deliveries.parquet")
    )
    args = parser.parse_args()
    output: Path = args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    frame = simulate_kolkata_deliveries(args.rows, args.seed)
    frame.to_parquet(output, index=False)
    print(f"Wrote {len(frame):,} explicitly simulated records to {output}")


if __name__ == "__main__":
    main()
