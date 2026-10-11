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

## Deployment checks

- Run `make check`, `make quality`, and `make dashboard-snapshot` locally.
- Start `make dashboard` against the snapshot before publishing it.
- Confirm the Streamlit app shows demand, OD, KPI, model-evaluation, and health views.
- Rotate or replace artifact URLs when the snapshot is refreshed. A deployment is read-only; ingestion, dbt, training, and Dagster remain local.
