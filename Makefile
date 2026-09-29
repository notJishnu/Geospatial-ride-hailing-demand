.PHONY: install lock format format-check lint test check download download-tlc download-ref download-weather dbt-debug dbt-build

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

dbt-debug:
	uv run dbt --project-dir dbt_project --profiles-dir dbt_project debug

dbt-build:
	uv run dbt --project-dir dbt_project --profiles-dir dbt_project build
