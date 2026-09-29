"""Download the TLC taxi-zone lookup and source geometry archive."""

from __future__ import annotations

import logging
import zipfile
from pathlib import Path

import polars as pl

from ingestion.download_utils import (
    DownloadManifest,
    download_file,
    matches_manifest,
    write_manifest,
)
from ingestion.settings import load_settings

REQUIRED_ZONE_COLUMNS = {"LocationID", "Borough", "Zone", "service_zone"}


def validate_zone_lookup(path: Path) -> None:
    """Validate lookup shape without transforming the official source CSV."""
    columns = set(pl.read_csv(path, n_rows=1).columns)
    missing = REQUIRED_ZONE_COLUMNS - columns
    if missing:
        raise ValueError(f"Zone lookup misses required columns: {sorted(missing)}")
    duplicated = pl.read_csv(path).select(pl.col("LocationID").is_duplicated().any()).item()
    if duplicated:
        raise ValueError("Zone lookup contains duplicate LocationID values")


def extract_zone_archive(archive_path: Path, destination: Path) -> None:
    """Safely extract the official shapefile archive once for later geospatial reads."""
    if destination.exists():
        logging.getLogger(__name__).info("Zone archive already extracted; skipping %s", destination)
        return
    destination.mkdir(parents=True)
    resolved_destination = destination.resolve()
    try:
        with zipfile.ZipFile(archive_path) as archive:
            for member in archive.infolist():
                target = (destination / member.filename).resolve()
                if not target.is_relative_to(resolved_destination):
                    raise ValueError(f"Unsafe member in zone archive: {member.filename}")
            archive.extractall(destination)
    except Exception:
        # The directory is created solely by this operation and contains only failed extraction output.
        for child in destination.rglob("*"):
            if child.is_file():
                child.unlink()
        destination.rmdir()
        raise


def _download_source(
    url: str, destination: Path, manifest_path: Path, settings: dict
) -> DownloadManifest | None:
    if destination.exists() and manifest_path.exists():
        if not matches_manifest(destination, manifest_path):
            raise ValueError(f"Existing source checksum does not match manifest: {destination}")
        logging.getLogger(__name__).info(
            "Source and manifest already exist; skipping %s", destination
        )
        return None
    if destination.exists() or manifest_path.exists():
        raise FileExistsError(
            f"Incomplete idempotency state for {destination}; inspect before retrying"
        )
    options = settings["ingestion"]
    manifest = download_file(
        url,
        destination,
        min_file_size_bytes=options["min_file_size_bytes"],
        timeout_seconds=options["timeout_seconds"],
        chunk_size_bytes=options["chunk_size_bytes"],
    )
    write_manifest(manifest, manifest_path)
    return manifest


def download_reference_data(settings: dict) -> None:
    """Acquire TLC zone sources, validate the lookup, and unpack geometry for local use."""
    source_dir = Path(settings["paths"]["reference"]) / "sources"
    manifest_dir = Path(settings["paths"]["manifests"]) / "reference"
    zones = settings["sources"]["zones"]
    lookup_path = source_dir / "taxi_zone_lookup.csv"
    lookup_manifest = _download_source(
        zones["lookup_url"], lookup_path, manifest_dir / "taxi_zone_lookup.json", settings
    )
    if lookup_manifest is not None:
        try:
            validate_zone_lookup(lookup_path)
        except Exception:
            lookup_path.unlink(missing_ok=True)
            (manifest_dir / "taxi_zone_lookup.json").unlink(missing_ok=True)
            raise

    archive_path = source_dir / "taxi_zones.zip"
    _download_source(
        zones["geometry_url"], archive_path, manifest_dir / "taxi_zones.json", settings
    )
    extract_zone_archive(
        archive_path, Path(settings["paths"]["reference"]) / "zones" / "taxi_zones"
    )


def main() -> None:
    """Run reference-data ingestion."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    download_reference_data(load_settings())


if __name__ == "__main__":
    main()
