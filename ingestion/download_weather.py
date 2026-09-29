"""Retrieve hourly NYC weather from the Open-Meteo historical API."""

from __future__ import annotations

import argparse
import calendar
import hashlib
import logging
import os
from datetime import date
from pathlib import Path

import polars as pl
import requests

from ingestion.download_tlc import parse_month
from ingestion.download_utils import DownloadManifest, matches_manifest, write_manifest
from ingestion.settings import load_settings


def month_date_range(month: str) -> tuple[date, date]:
    """Return inclusive first and final dates for a YYYY-MM month."""
    year, month_number = (int(part) for part in parse_month(month).split("-"))
    return date(year, month_number, 1), date(year, month_number, calendar.monthrange(year, month_number)[1])


def fetch_hourly_weather(start: date, end: date, settings: dict) -> dict:
    """Call Open-Meteo once for the configured local-time hourly variables."""
    weather = settings["sources"]["weather"]
    response = requests.get(
        weather["archive_url"],
        params={
            "latitude": weather["latitude"],
            "longitude": weather["longitude"],
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "hourly": ",".join(weather["hourly"]),
            "timezone": weather["timezone"],
        },
        timeout=settings["ingestion"]["timeout_seconds"],
    )
    response.raise_for_status()
    payload = response.json()
    if "hourly" not in payload or "time" not in payload["hourly"]:
        raise ValueError("Open-Meteo response lacks hourly time data")
    return payload


def normalize_weather(payload: dict, timezone: str) -> pl.DataFrame:
    """Convert aligned Open-Meteo arrays into a typed local-time weather table."""
    hourly = payload["hourly"]
    expected_length = len(hourly["time"])
    columns: dict[str, list] = {"weather_time_local": hourly["time"]}
    for name, values in hourly.items():
        if name != "time":
            if len(values) != expected_length:
                raise ValueError(f"Open-Meteo hourly array has inconsistent length: {name}")
            columns[name] = values
    return pl.DataFrame(columns).with_columns(pl.lit(timezone).alias("timezone"))


def write_weather_partition(frame: pl.DataFrame, month: str, settings: dict) -> DownloadManifest:
    """Write one normalized weather partition atomically and record its checksum."""
    year, month_number = parse_month(month).split("-")
    destination = Path(settings["paths"]["reference"]) / "weather" / f"year={year}" / f"month={month_number}" / "weather_hourly.parquet"
    manifest_path = Path(settings["paths"]["manifests"]) / "weather" / f"weather_hourly_{month}.json"
    if destination.exists() or manifest_path.exists():
        raise FileExistsError(f"Refusing to overwrite weather partition: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".parquet.part")
    frame.write_parquet(temporary)
    data = temporary.read_bytes()
    if len(data) < settings["ingestion"]["min_file_size_bytes"]:
        temporary.unlink(missing_ok=True)
        raise ValueError("Weather partition is unexpectedly small")
    os.replace(temporary, destination)
    manifest = DownloadManifest("Open-Meteo historical API", str(destination), len(data), hashlib.sha256(data).hexdigest())
    write_manifest(manifest, manifest_path)
    return manifest


def download_month(month: str, settings: dict) -> DownloadManifest | None:
    """Idempotently download, normalize, and manifest one month of hourly weather."""
    month = parse_month(month)
    manifest_path = Path(settings["paths"]["manifests"]) / "weather" / f"weather_hourly_{month}.json"
    year, month_number = month.split("-")
    destination = Path(settings["paths"]["reference"]) / "weather" / f"year={year}" / f"month={month_number}" / "weather_hourly.parquet"
    if destination.exists() and manifest_path.exists():
        if not matches_manifest(destination, manifest_path):
            raise ValueError(f"Existing weather checksum does not match manifest: {destination}")
        logging.getLogger(__name__).info("Weather partition already exists; skipping %s", month)
        return None
    if destination.exists() or manifest_path.exists():
        raise FileExistsError(f"Incomplete idempotency state for weather {month}; inspect before retrying")
    start, end = month_date_range(month)
    payload = fetch_hourly_weather(start, end, settings)
    frame = normalize_weather(payload, settings["sources"]["weather"]["timezone"])
    return write_weather_partition(frame, month, settings)


def main() -> None:
    """Run configured or explicitly requested weather downloads."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--month", action="append", dest="months")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = load_settings()
    for month in args.months or settings["months"]:
        download_month(month, settings)


if __name__ == "__main__":
    main()
