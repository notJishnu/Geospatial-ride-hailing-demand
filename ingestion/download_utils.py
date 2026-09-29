"""Shared, atomic download and manifest helpers."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import asdict, dataclass
from pathlib import Path

import requests

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class DownloadManifest:
    """Audit record for one completed source download."""

    source_url: str
    destination: str
    bytes_written: int
    sha256: str


def download_file(
    url: str,
    destination: Path,
    *,
    min_file_size_bytes: int,
    timeout_seconds: int,
    chunk_size_bytes: int,
) -> DownloadManifest:
    """Stream a file once, verify it, and publish it atomically without overwriting raw data."""
    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite existing source file: {destination}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(f"{destination.suffix}.part")
    if temporary.exists():
        temporary.unlink()

    digest = hashlib.sha256()
    bytes_written = 0
    try:
        with requests.get(url, stream=True, timeout=timeout_seconds) as response:
            response.raise_for_status()
            with temporary.open("wb") as output:
                for chunk in response.iter_content(chunk_size=chunk_size_bytes):
                    if chunk:
                        output.write(chunk)
                        digest.update(chunk)
                        bytes_written += len(chunk)
        if bytes_written < min_file_size_bytes:
            raise ValueError(f"Downloaded file is too small ({bytes_written} bytes): {url}")
        os.replace(temporary, destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise

    manifest = DownloadManifest(url, str(destination), bytes_written, digest.hexdigest())
    LOGGER.info("Downloaded %s (%d bytes, sha256=%s)", destination, bytes_written, manifest.sha256)
    return manifest


def write_manifest(manifest: DownloadManifest, manifest_path: Path) -> None:
    """Persist an audit manifest without modifying the downloaded source file."""
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("x", encoding="utf-8") as output:
        json.dump(asdict(manifest), output, indent=2, sort_keys=True)
        output.write("\n")


def matches_manifest(destination: Path, manifest_path: Path) -> bool:
    """Return whether a local file still matches its recorded byte size and SHA-256."""
    with manifest_path.open(encoding="utf-8") as source:
        manifest = json.load(source)
    if destination.stat().st_size != manifest["bytes_written"]:
        return False
    digest = hashlib.sha256()
    with destination.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest() == manifest["sha256"]
