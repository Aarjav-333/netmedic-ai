"""Incident endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.engine import SimulationEngine, get_engine
from app.models.incident import Incident, IncidentSummary

router = APIRouter(prefix="/incidents", tags=["incidents"])


@router.get("", response_model=list[IncidentSummary])
async def list_incidents(engine: SimulationEngine = Depends(get_engine)) -> list[IncidentSummary]:
    return engine.incidents.summaries()


@router.get("/active", response_model=Incident | None)
async def active_incident(engine: SimulationEngine = Depends(get_engine)) -> Incident | None:
    return engine.incidents.active


@router.get("/{incident_id}", response_model=Incident)
async def get_incident(incident_id: str, engine: SimulationEngine = Depends(get_engine)) -> Incident:
    incident = engine.incidents.get(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail=f"Unknown incident {incident_id!r}")
    return incident
