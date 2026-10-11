FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY ingestion ./ingestion
COPY ml ./ml
COPY api ./api

RUN pip install --no-cache-dir ".[ml,serving]"

ENV PYTHONUNBUFFERED=1
ENV NYC_MOBILITY_ROOT=/app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
