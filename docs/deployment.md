# Streamlit Cloud deployment

## Build the dashboard snapshot locally

After Gold models, training, and quality checks have completed, run:

```powershell
make dashboard-snapshot
```

This creates `data/dashboard/nyc_dashboard_snapshot.duckdb`. It contains only dashboard marts, row-count health metadata, and saved metric/report JSON. It excludes immutable Bronze files and the 19M-row trip fact table. The snapshot is Git-ignored; publish it to approved artifact storage or a GitHub Release rather than commit it.

## Configure Streamlit Cloud

1. Create an app from this repository with main file `dashboard/app.py`. In **Advanced settings**, select Python 3.11 to match this project.
2. Streamlit Cloud installs `requirements.txt` automatically.
3. In the app's Secrets settings, add the signed or approved artifact URL and its SHA-256:

```toml
DASHBOARD_WAREHOUSE_URL = "https://your-approved-artifact-host/nyc_dashboard_snapshot.duckdb"
DASHBOARD_WAREHOUSE_SHA256 = "replace-with-sha256"
```

The app downloads the snapshot once into its temporary cache and verifies the optional checksum before opening DuckDB read-only. Never add an MLflow directory, full warehouse, raw TLC data, or credentials to Git.

## Scheduled snapshot refresh

The `refresh-dashboard-snapshot.yml` workflow runs each Monday at 08:17 UTC and can also be run manually from the **Actions** tab. It downloads a refreshed full warehouse, builds a compact snapshot, and replaces the stable `dashboard-data-latest` GitHub Release asset.

Add these repository **Actions secrets** before enabling it:

```text
DASHBOARD_SOURCE_WAREHOUSE_URL=https://approved-private-or-signed-host/nyc_mobility.duckdb
DASHBOARD_SOURCE_WAREHOUSE_SHA256=optional-sha256-of-that-source-file
```

`DASHBOARD_SOURCE_WAREHOUSE_URL` must be a direct URL that GitHub Actions can download without an interactive login. Leave the checksum secret empty only when the source storage already verifies integrity. The workflow never commits the source warehouse or snapshot to Git.

For automatic updates, configure Streamlit with the stable release manifest instead of a static snapshot URL:

```toml
DASHBOARD_WAREHOUSE_MANIFEST_URL = "https://github.com/notJishnu/Geospatial-ride-hailing-demand/releases/download/dashboard-data-latest/dashboard-manifest.json"
```

The manifest supplies the current direct asset URL and SHA-256. The dashboard checks for a new manifest at most once an hour, downloads a changed snapshot, and verifies its checksum. Do not also configure `DASHBOARD_WAREHOUSE_URL` or `DASHBOARD_WAREHOUSE_SHA256` when using the manifest.

## Deployment checks

- Run `make check`, `make quality`, and `make dashboard-snapshot` locally.
- Start `make dashboard` against the snapshot before publishing it.
- Confirm the Streamlit app shows demand, OD, KPI, model-evaluation, and health views.
- Rotate or replace artifact URLs when the snapshot is refreshed. A deployment is read-only; ingestion, dbt, training, and Dagster remain local.
