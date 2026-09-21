"""Liveness endpoint."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    time: datetime


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    from app.main import APP_VERSION  # local import avoids a circular import at module load

    return HealthResponse(
        status="ok",
        service="netmedic-ai-backend",
        version=APP_VERSION,
        time=datetime.now(timezone.utc),
    )
