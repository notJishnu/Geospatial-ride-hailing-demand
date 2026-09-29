"""Configuration loading for ingestion commands."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_settings(path: Path = Path("config/settings.yaml")) -> dict[str, Any]:
    """Load the project YAML settings file into a plain mapping."""
    with path.open(encoding="utf-8") as config_file:
        settings = yaml.safe_load(config_file)
    if not isinstance(settings, dict):
        raise ValueError(f"Settings file must contain a mapping: {path}")
    return settings
