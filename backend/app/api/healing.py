"""Healing control endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.engine import SimulationEngine, get_engine
from app.models.incident import HealingModeRequest, HealingModeResponse, Incident

router = APIRouter(prefix="/healing", tags=["healing"])


@router.get("/mode", response_model=HealingModeResponse)
async def get_mode(engine: SimulationEngine = Depends(get_engine)) -> HealingModeResponse:
    return HealingModeResponse(auto_heal=engine.incidents.auto_heal)


@router.post("/mode", response_model=HealingModeResponse)
async def set_mode(request: HealingModeRequest, engine: SimulationEngine = Depends(get_engine)) -> HealingModeResponse:
    enabled = await engine.set_auto_heal(request.auto_heal)
    return HealingModeResponse(auto_heal=enabled)


@router.post("/{incident_id}/execute", response_model=Incident)
async def execute_healing(incident_id: str, engine: SimulationEngine = Depends(get_engine)) -> Incident:
    """Approve and run the recommended remediation for an incident waiting in DIAGNOSED."""
    try:
        return await engine.execute_healing(incident_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown incident {incident_id!r}") from None
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
