"""Root-cause analysis endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.engine import SimulationEngine, get_engine
from app.models.diagnosis import Diagnosis

router = APIRouter(prefix="/diagnosis", tags=["diagnosis"])


@router.get("/current", response_model=Diagnosis | None)
async def current_diagnosis(engine: SimulationEngine = Depends(get_engine)) -> Diagnosis | None:
    """Live diagnosis of whatever detection currently flags (null when the network is healthy)."""
    return engine.diagnosis
