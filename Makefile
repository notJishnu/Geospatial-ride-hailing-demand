.PHONY: install lock format format-check lint test check download download-tlc download-ref download-weather profile dbt-debug dbt-build train-demand train-eta dagster-ui dagster-partition api docker-api dashboard quality drift simulate-kolkata replay

install:
	uv sync --all-extras

lock:
	uv lock

format:
	uv run ruff format .

format-check:
	uv run ruff format --check .

lint:
	uv run ruff check .

test:
	uv run pytest

check: format-check lint test

download:
	uv run python -m ingestion.download_tlc
	uv run python -m ingestion.download_reference
	uv run python -m ingestion.download_weather

download-tlc:
	uv run python -m ingestion.download_tlc

download-ref:
	uv run python -m ingestion.download_reference

download-weather:
	uv run python -m ingestion.download_weather

build-calendar:
	uv run python -m ingestion.build_calendar

profile:
	uv run python -m profiling.profile_hvfhv

dbt-debug:
	uv run dbt debug --project-dir dbt_project --profiles-dir dbt_project

dbt-build:
	uv run dbt build --project-dir dbt_project --profiles-dir dbt_project

train-demand:
	uv run python -m ml.train_demand

train-eta:
	uv run python -m ml.train_eta

dagster-ui:
	uv run dagster dev -w orchestration/workspace.yaml

dagster-partition:
	uv run python -m orchestration.dagster_project.run_partition --partition 2024-01-01

api:
	uv run uvicorn api.main:app --reload --host 127.0.0.1 --port 8000

docker-api:
	docker compose up --build eta-api

dashboard:
	uv run streamlit run dashboard/app.py

quality:
	uv run python -m monitoring.dq_checks

drift:
	uv run python -m monitoring.drift_report

simulate-kolkata:
	uv run python -m stretch.kolkata_simulated

replay:
	uv run python -m stretch.replay --month 2024-01 --limit 100 --speedup 3600
