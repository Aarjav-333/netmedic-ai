"""AI explanation endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.ai.factory import provider_status
from app.engine import SimulationEngine, get_engine
from app.models.ai import AIExplanation, AIProviderStatus

router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/provider", response_model=AIProviderStatus)
async def get_provider(engine: SimulationEngine = Depends(get_engine)) -> AIProviderStatus:
    return provider_status(engine.ai_provider)


@router.post("/explain/{incident_id}", response_model=AIExplanation)
async def explain_incident(incident_id: str, engine: SimulationEngine = Depends(get_engine)) -> AIExplanation:
    """(Re)generate the explanation for an incident that has a diagnosis."""
    incident = engine.incidents.get(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail=f"Unknown incident {incident_id!r}")
    if incident.diagnosis is None:
        raise HTTPException(status_code=409, detail="Incident has no diagnosis yet")
    return await engine.explain_incident(incident)
