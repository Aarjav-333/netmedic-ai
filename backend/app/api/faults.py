"""Fault injection endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.engine import SimulationEngine, get_engine
from app.models.faults import (
    ActiveFaultSchema,
    FaultListResponse,
    InjectFaultRequest,
    ResetResponse,
)
from app.simulation.faults import FAULT_CATALOG, FaultInjectionError

router = APIRouter(prefix="/faults", tags=["faults"])


@router.get("", response_model=FaultListResponse)
async def list_faults(engine: SimulationEngine = Depends(get_engine)) -> FaultListResponse:
    return FaultListResponse(
        active=[f.to_schema() for f in engine.faults.active],
        catalog=list(FAULT_CATALOG),
    )


@router.post("/inject", response_model=ActiveFaultSchema, status_code=201)
async def inject_fault(
    request: InjectFaultRequest, engine: SimulationEngine = Depends(get_engine)
) -> ActiveFaultSchema:
    try:
        fault = await engine.inject_fault(request)
    except FaultInjectionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return fault.to_schema()


@router.post("/reset", response_model=ResetResponse)
async def reset_faults(engine: SimulationEngine = Depends(get_engine)) -> ResetResponse:
    cleared = await engine.reset_async()
    return ResetResponse(cleared_faults=cleared, message="Simulation reset to healthy baseline")


@router.delete("/{fault_id}", response_model=ActiveFaultSchema)
async def clear_fault(fault_id: str, engine: SimulationEngine = Depends(get_engine)) -> ActiveFaultSchema:
    fault = await engine.clear_fault(fault_id)
    if fault is None:
        raise HTTPException(status_code=404, detail=f"No active fault {fault_id!r}")
    return fault.to_schema()
