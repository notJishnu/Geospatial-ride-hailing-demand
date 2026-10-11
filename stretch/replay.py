"""Deterministically replay completed trip events as JSON Lines for local demos."""

from __future__ import annotations

import argparse
import json
import time
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import duckdb

from ingestion.settings import load_settings
from monitoring.drift_report import validate_month


def replay_delays(timestamps: list[float], speedup: float) -> list[float]:
    """Return bounded inter-event delays for a timestamp sequence and replay speed."""
    if speedup <= 0:
        raise ValueError("speedup must be positive")
    if not timestamps:
        return []
    return [
        0.0,
        *[
            max(0.0, (current - previous) / speedup)
            for previous, current in zip(timestamps, timestamps[1:])
        ],
    ]


def event_stream(warehouse: Path, month: str, limit: int) -> Iterator[dict[str, object]]:
    """Yield historical trip starts in timestamp order as a local replay source."""
    connection = duckdb.connect(str(warehouse), read_only=True)
    try:
        rows = connection.execute(
            """
            select trip_id, pickup_datetime, pickup_zone_id, dropoff_zone_id
            from fct_trips
            where ingestion_month = ?
            order by pickup_datetime, trip_id
            limit ?
            """,
            [validate_month(month), limit],
        ).fetchall()
    finally:
        connection.close()
    for trip_id, pickup_datetime, pickup_zone_id, dropoff_zone_id in rows:
        yield {
            "event_type": "trip_requested_replay",
            "trip_id": trip_id,
            "event_time": pickup_datetime.isoformat(),
            "pickup_zone_id": pickup_zone_id,
            "dropoff_zone_id": dropoff_zone_id,
            "is_replay": True,
        }


def main() -> None:
    """Emit replay events to stdout; no queue, broker, or production stream is created."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--month", default="2024-01")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--speedup", type=float, default=3600.0)
    args = parser.parse_args()
    settings = load_settings()
    events = list(event_stream(Path(settings["paths"]["warehouse"]), args.month, args.limit))
    timestamps = [datetime.fromisoformat(str(event["event_time"])).timestamp() for event in events]
    for delay, event in zip(replay_delays(timestamps, args.speedup), events, strict=True):
        if delay:
            time.sleep(delay)
        print(json.dumps(event))


if __name__ == "__main__":
    main()
