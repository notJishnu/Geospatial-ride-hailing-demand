"""Build a local holiday and manual-event calendar for configured source months."""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from pathlib import Path

import holidays
import polars as pl

from ingestion.download_tlc import parse_month
from ingestion.settings import load_settings


def month_dates(month: str) -> list[date]:
    """Return every local calendar date in a configured YYYY-MM month."""
    year, month_number = (int(part) for part in parse_month(month).split("-"))
    start = date(year, month_number, 1)
    return [
        start + timedelta(days=offset)
        for offset in range(calendar.monthrange(year, month_number)[1])
    ]


def build_calendar(settings: dict) -> pl.DataFrame:
    """Create date-level US/New York holiday flags and attach configured manual events."""
    dates = [day for month in settings["months"] for day in month_dates(month)]
    ny_holidays = holidays.US(years=sorted({day.year for day in dates}), subdiv="NY")
    events = pl.read_csv(Path("config/events.csv"), try_parse_dates=True)
    event_map = {
        date.fromisoformat(str(row["event_date"])): row
        for row in events.to_dicts()
        if row.get("event_date") is not None
    }
    return pl.DataFrame(
        [
            {
                "calendar_date": day,
                "is_holiday": day in ny_holidays,
                "holiday_name": ny_holidays.get(day),
                "event_name": event_map.get(day, {}).get("event_name"),
                "event_borough": event_map.get(day, {}).get("borough"),
                "event_notes": event_map.get(day, {}).get("notes"),
            }
            for day in dates
        ]
    )


def main() -> None:
    """Write the configured date-level calendar as an ignored reference Parquet file."""
    settings = load_settings()
    destination = Path(settings["paths"]["reference"]) / "calendar" / "calendar_dates.parquet"
    destination.parent.mkdir(parents=True, exist_ok=True)
    build_calendar(settings).write_parquet(destination)


if __name__ == "__main__":
    main()
