"""Demo mode endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.demo import SCENARIOS
from app.engine import SimulationEngine, get_engine

router = APIRouter(prefix="/demo", tags=["demo"])


class DemoRunRequest(BaseModel):
    scenario: str = "congestion"


class ScenarioInfo(BaseModel):
    key: str
    title: str
    description: str
    target_id: str


@router.get("/scenarios", response_model=list[ScenarioInfo])
async def list_scenarios() -> list[ScenarioInfo]:
    return [ScenarioInfo(key=s.key, title=s.title, description=s.description, target_id=s.target_id) for s in SCENARIOS.values()]


@router.get("/status")
async def demo_status(engine: SimulationEngine = Depends(get_engine)) -> dict[str, Any]:
    return engine.demo.state.to_dict()


@router.post("/run")
async def run_demo(request: DemoRunRequest | None = None, engine: SimulationEngine = Depends(get_engine)) -> dict[str, Any]:
    scenario = request.scenario if request else "congestion"
    try:
        state = await engine.demo.start(scenario)
    except KeyError:
        raise HTTPException(status_code=400, detail=f"Unknown scenario {scenario!r}") from None
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return state.to_dict()


@router.post("/stop")
async def stop_demo(engine: SimulationEngine = Depends(get_engine)) -> dict[str, Any]:
    state = await engine.demo.stop()
    return state.to_dict()
