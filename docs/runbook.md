# Runbook

## Phase 0–1 local setup

Use Python 3.11 only. Create the locked environment with `uv sync --all-extras`, then run `make check`.

## Ingestion recovery

Never overwrite Bronze data. Each successful download has a separate SHA-256 manifest in `data/manifests/`. If a destination and its manifest do not both exist, inspect the incomplete state before retrying. A `.part` file is an interrupted transfer and may be safely removed after confirming no downloader is running.

## Source limitations

TLC zone records contain zone IDs, not precise pickup/dropoff GPS coordinates. Open-Meteo is requested in `America/New_York`; later silver transformations must test DST-boundary joins explicitly.

## Silver backfill

Run `dbt build --project-dir dbt_project --profiles-dir dbt_project --vars '{target_month: 2024-01}'` from the repository root. This processes one immutable monthly partition into either `silver_trips_valid` or `silver_trips_quarantine`. Zone IDs 264/265 remain in valid Silver data with `is_unknown_or_outside_nyc = true`; do not use them as geographic training targets.
