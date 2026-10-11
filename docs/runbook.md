# Runbook

## Phase 0–1 local setup

Use Python 3.11 only. Create the locked environment with `uv sync --all-extras`, then run `make check`.

## Ingestion recovery

Never overwrite Bronze data. Each successful download has a separate SHA-256 manifest in `data/manifests/`. If a destination and its manifest do not both exist, inspect the incomplete state before retrying. A `.part` file is an interrupted transfer and may be safely removed after confirming no downloader is running.

## Source limitations

TLC zone records contain zone IDs, not precise pickup/dropoff GPS coordinates. Open-Meteo is requested in `America/New_York`; later silver transformations must test DST-boundary joins explicitly.

## Silver backfill

Run `dbt build --project-dir dbt_project --profiles-dir dbt_project --vars '{target_month: 2024-01}'` from the repository root. This processes one immutable monthly partition into either `silver_trips_valid` or `silver_trips_quarantine`. Zone IDs 264/265 remain in valid Silver data with `is_unknown_or_outside_nyc = true`; do not use them as geographic training targets.

## Gold build

Run `python -m ingestion.build_calendar`, then `dbt build --project-dir dbt_project --profiles-dir dbt_project --select +gold+ --vars '{target_month: 2024-01}'`. Gold facts retain valid trips; geographic zone, OD, and demand marts exclude zone IDs 264/265. The holiday calendar is generated from the configured month list and manual events in `config/events.csv`.

## Demand model

Run `python -m ml.train_demand` (or `make train-demand`) after the Gold build. This saves a local LightGBM candidate and metrics under `artifacts/demand/` and logs the run to local `mlruns/`; neither is committed. The model evaluates chronological validation/test windows and writes the WAPE-selected champion to `metrics.json`.

Run `python -m ml.train_eta` (or `make train-eta`) after the Gold build. This builds strictly prior-hour ETA aggregates from Gold, tunes a LightGBM candidate with Optuna, evaluates the final chronological holdout, and writes model, metrics, and SHAP artifacts under `artifacts/eta/`. The MAE-selected candidate is tagged in MLflow; its registered version must be reviewed before serving. Review the split sizes and baseline comparison before promoting any model; the January-only MVP is not a production deployment.

## Dagster orchestration

Run `make dagster-ui`, then open the local Dagster UI. The `monthly_refresh_job` is partitioned by calendar month and materializes reference data, Bronze trips, weather, and dbt Silver/Gold models. The first scheduled candidate runs at 08:00 America/New_York on the fifth of each month for the preceding month; its default state is stopped so it cannot begin downloading new months unexpectedly. Enable it in the UI only after adding the desired month to `config/settings.yaml` for the holiday calendar.

Use the UI's Backfill action to select completed month partitions, or run `make dagster-partition` for the configured January check. Every asset is idempotent, has bounded retries, and sends failure details to the local Dagster event log. No external alert channel is configured; add one only when an approved notification destination exists.

## ETA API serving

Run `make api` for local development, then request `GET /health`. The service loads the local MLflow registry model `nyc_eta_lightgbm` version `1` and opens DuckDB read-only. `POST /predict/eta` requires pickup and dropoff zone IDs plus an offset-aware `request_time`; `precipitation_mm` is optional.

The service builds route history from trips before the request's completed hour only. It never accepts actual trip miles. Its `interval_p10_p90` is a symmetric band using the final holdout P90 absolute error (about 7.76 minutes), so it is an empirical error band, not a calibrated probabilistic interval. Supply precipitation from an approved forecast source for future requests; the locally stored historical weather is only a fallback for historical requests.

To run the container, first train and register the ETA model locally, then use `make docker-api`. Docker mounts `mlruns/` and `data/warehouse/` read-only; neither is included in the image.

## Streamlit dashboard

Run `make dashboard` after building Gold models. The dashboard reads DuckDB in read-only mode and caches tables for ten minutes. It has demand-map, zone-KPI, OD-flow, ETA-evaluation, forecast-evaluation, and data-health views. Map points are TLC zone centroids, not trip GPS coordinates; model pages report saved holdout metrics and never invent future forecasts.
