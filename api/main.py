"""FastAPI application for pre-trip ETA predictions."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status

from api.model_loader import EtaPredictor, default_settings
from api.schemas import EtaPredictionRequest, EtaPredictionResponse, HealthResponse

LOGGER = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Create an application that loads its MLflow model during startup."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            app.state.predictor = EtaPredictor(default_settings())
            app.state.load_error = None
        except Exception as error:  # health must remain observable on a bad local deployment
            LOGGER.exception("ETA model failed to load")
            app.state.predictor = None
            app.state.load_error = str(error)
        yield

    app = FastAPI(title="NYC Mobility ETA API", version="0.1.0", lifespan=lifespan)

    @app.get("/health", response_model=HealthResponse)
    async def health(request: Request) -> HealthResponse:
        predictor = request.app.state.predictor
        if predictor is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="ETA model is unavailable",
            )
        return HealthResponse(status="ok", model_version=predictor.model_version)

    @app.post("/predict/eta", response_model=EtaPredictionResponse)
    async def predict_eta(payload: EtaPredictionRequest, request: Request) -> EtaPredictionResponse:
        predictor: EtaPredictor | None = request.app.state.predictor
        if predictor is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="ETA model is unavailable",
            )
        try:
            features = predictor.build_features(
                payload.pickup_zone_id,
                payload.dropoff_zone_id,
                payload.request_time,
                payload.precipitation_mm,
            )
            eta_minutes = predictor.predict_minutes(features)
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
            ) from error
        return EtaPredictionResponse(
            eta_minutes=round(eta_minutes, 2),
            interval_p10_p90=tuple(
                round(value, 2) for value in predictor.prediction_interval(eta_minutes)
            ),
            model_version=predictor.model_version,
        )

    return app


app = create_app()
