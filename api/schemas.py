"""Request and response contracts for the ETA service."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EtaPredictionRequest(BaseModel):
    """Inputs available before an HVFHV trip begins."""

    model_config = ConfigDict(extra="forbid")

    pickup_zone_id: int = Field(ge=1, le=263)
    dropoff_zone_id: int = Field(ge=1, le=263)
    request_time: datetime
    precipitation_mm: float | None = Field(default=None, ge=0, le=500)

    @field_validator("request_time")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        """Reject ambiguous local timestamps, especially around DST transitions."""
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("request_time must include a UTC offset, for example -05:00")
        return value


class EtaPredictionResponse(BaseModel):
    """A serving prediction and its empirical error band."""

    eta_minutes: float = Field(ge=0)
    interval_p10_p90: tuple[float, float]
    model_version: str


class HealthResponse(BaseModel):
    """Readiness state of the lazily loaded model service."""

    status: str
    model_version: str | None = None
