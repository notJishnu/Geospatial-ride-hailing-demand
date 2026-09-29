"""Download and validate immutable monthly TLC HVFHV Parquet files."""

from __future__ import annotations

import argparse
import logging
import re
from pathlib import Path

import pyarrow.parquet as pq

from ingestion.download_utils import (
    DownloadManifest,
    download_file,
    matches_manifest,
    write_manifest,
)
from ingestion.settings import load_settings

MONTH_PATTERN = re.compile(r"^20\d{2}-(0[1-9]|1[0-2])$")


def parse_month(value: str) -> str:
    """Validate and return a month in YYYY-MM form."""
    if not MONTH_PATTERN.fullmatch(value):
        raise ValueError(f"Expected YYYY-MM, received {value!r}")
    return value


def build_tlc_url(month: str, template: str) -> str:
    """Build the official TLC monthly-file URL from configured template."""
    return template.format(month=parse_month(month))


def verify_parquet(path: Path) -> None:
    """Confirm that a downloaded file is readable Parquet and has at least one column."""
    metadata = pq.ParquetFile(path).metadata
    if metadata is None or metadata.num_columns == 0:
        raise ValueError(f"Invalid or empty Parquet metadata: {path}")


def download_month(month: str, settings: dict) -> DownloadManifest | None:
    """Idempotently download, validate, and manifest one monthly TLC file."""
    month = parse_month(month)
    year, month_number = month.split("-")
    destination = (
        Path(settings["paths"]["bronze"])
        / "hvfhv"
        / f"year={year}"
        / f"month={month_number}"
        / f"fhvhv_tripdata_{month}.parquet"
    )
    manifest_path = Path(settings["paths"]["manifests"]) / "tlc" / f"fhvhv_tripdata_{month}.json"
    if destination.exists() and manifest_path.exists():
        if not matches_manifest(destination, manifest_path):
            raise ValueError(f"Existing source checksum does not match manifest: {destination}")
        logging.getLogger(__name__).info("Source and manifest already exist; skipping %s", month)
        return None
    if destination.exists() or manifest_path.exists():
        raise FileExistsError(f"Incomplete idempotency state for {month}; inspect before retrying")

    options = settings["ingestion"]
    manifest = download_file(
        build_tlc_url(month, settings["sources"]["tlc"]["trip_data_url_template"]),
        destination,
        min_file_size_bytes=options["min_file_size_bytes"],
        timeout_seconds=options["timeout_seconds"],
        chunk_size_bytes=options["chunk_size_bytes"],
    )
    try:
        verify_parquet(destination)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    write_manifest(manifest, manifest_path)
    return manifest


def main() -> None:
    """Run configured or explicitly requested TLC month downloads."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--month", action="append", dest="months")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = load_settings()
    for month in args.months or settings["months"]:
        download_month(month, settings)


if __name__ == "__main__":
    main()
