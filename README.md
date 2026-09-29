# NYC Mobility Analytics

Local-first analytics and ML platform for NYC TLC High-Volume For-Hire Vehicle (HVFHV) trips.

## Setup

Install Python 3.11 and [uv](https://docs.astral.sh/uv/), then run:

```powershell
uv sync --all-extras
uv run pre-commit install
make check
```

## Initial ingestion

The configured first month is `2024-01`. Source files are idempotent: a completed source plus its SHA-256 manifest is skipped, while partial states fail safely for inspection.

```powershell
make download-ref
make download-tlc
make download-weather
```

Downloaded TLC files are immutable under `data/bronze/`; reference sources and normalized weather are ignored by Git..
