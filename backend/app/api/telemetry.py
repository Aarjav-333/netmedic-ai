"""Telemetry endpoints (current snapshot and compact history for charts)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.engine import SimulationEngine, get_engine
from app.models.telemetry import TelemetryHistoryResponse, TelemetrySnapshot

router = APIRouter(prefix="/telemetry", tags=["telemetry"])


@router.get("/current", response_model=TelemetrySnapshot)
async def current_telemetry(engine: SimulationEngine = Depends(get_engine)) -> TelemetrySnapshot:
    if engine.latest is None:
        raise HTTPException(status_code=503, detail="Telemetry not available yet")
    return engine.latest


@router.get("/history", response_model=TelemetryHistoryResponse)
async def telemetry_history(
    limit: int = Query(default=120, ge=1, le=240),
    engine: SimulationEngine = Depends(get_engine),
) -> TelemetryHistoryResponse:
    return TelemetryHistoryResponse(points=engine.metric_points(limit))
