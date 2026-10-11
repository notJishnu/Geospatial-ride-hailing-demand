"""API contract tests with a deterministic in-memory predictor."""

from __future__ import annotations

import asyncio
import platform

import httpx
import pandas as pd
import pytest

from api.main import create_app

pytestmark = pytest.mark.skipif(
    platform.system() == "Windows",
    reason="Windows event-loop socketpair is blocked in this local environment; run these HTTPX tests in Docker/CI.",
)


class FakePredictor:
    """Minimal predictor that verifies API request wiring without local artifacts."""

    model_version = "test-1"

    def build_features(self, pickup_zone_id: int, dropoff_zone_id: int, *_: object) -> pd.DataFrame:
        if pickup_zone_id == 999 or dropoff_zone_id == 999:
            raise ValueError("Unknown or unsupported NYC zone IDs: [999]")
        return pd.DataFrame(
            {"pickup_zone_id": [pickup_zone_id], "dropoff_zone_id": [dropoff_zone_id]}
        )

    def predict_minutes(self, _: pd.DataFrame) -> float:
        return 12.5

    def prediction_interval(self, _: float) -> tuple[float, float]:
        return 4.5, 20.5


def app_with_fake_predictor():
    """Build the app with its startup-loaded predictor replaced by a test double."""
    app = create_app()
    app.state.predictor = FakePredictor()
    return app


def request(app, method: str, path: str, **kwargs: object) -> httpx.Response:
    """Exercise the ASGI app directly without starting a network listener."""

    async def send() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(send())


def test_health_reports_loaded_model() -> None:
    response = request(app_with_fake_predictor(), "GET", "/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "model_version": "test-1"}


def test_predict_eta_returns_contract() -> None:
    response = request(
        app_with_fake_predictor(),
        "POST",
        "/predict/eta",
        json={
            "pickup_zone_id": 161,
            "dropoff_zone_id": 230,
            "request_time": "2024-01-15T09:30:00-05:00",
            "precipitation_mm": 1.2,
        },
    )
    assert response.status_code == 200
    assert response.json() == {
        "eta_minutes": 12.5,
        "interval_p10_p90": [4.5, 20.5],
        "model_version": "test-1",
    }


def test_predict_eta_rejects_naive_timestamp() -> None:
    response = request(
        app_with_fake_predictor(),
        "POST",
        "/predict/eta",
        json={
            "pickup_zone_id": 161,
            "dropoff_zone_id": 230,
            "request_time": "2024-01-15T09:30:00",
        },
    )
    assert response.status_code == 422
    assert "UTC offset" in response.text
