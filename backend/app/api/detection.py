"""Anomaly detection endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

import json

from app.config import BACKEND_DIR
from app.detection.detector import CONFIRM_TICKS
from app.engine import SimulationEngine, get_engine
from app.models.detection import DetectionResult, ModelInfoResponse
from app.models.edge import EdgeProfile

router = APIRouter(prefix="/detection", tags=["detection"])


@router.get("/current", response_model=DetectionResult)
async def current_detection(engine: SimulationEngine = Depends(get_engine)) -> DetectionResult:
    if engine.detection is None:
        raise HTTPException(status_code=503, detail="Detection not available yet")
    return engine.detection


@router.get("/model", response_model=ModelInfoResponse)
async def model_info(engine: SimulationEngine = Depends(get_engine)) -> ModelInfoResponse:
    meta = engine.detector.metadata
    if meta is None:
        raise HTTPException(status_code=503, detail="Model not trained yet")
    return ModelInfoResponse(
        algorithm="IsolationForest (scikit-learn)",
        trained_at=meta.trained_at,
        n_samples=meta.n_samples,
        feature_names=meta.feature_names,
        contamination=meta.contamination,
        n_estimators=meta.n_estimators,
        threshold=meta.threshold,
        severity_span=meta.severity_span,
        confirm_ticks=CONFIRM_TICKS,
    )


EDGE_PROFILE_PATH = BACKEND_DIR / "data" / "edge_profile.json"


@router.get("/edge", response_model=EdgeProfile | None)
async def edge_profile() -> EdgeProfile | None:
    """The on-device detector's validation + Qualcomm AI Hub profile.

    Returns null until `scripts/edge_detector.py` has been run. Read-only: the figures
    come from a real compile/profile job, never from anything computed at request time.
    """
    if not EDGE_PROFILE_PATH.exists():
        return None
    try:
        return EdgeProfile.model_validate(json.loads(EDGE_PROFILE_PATH.read_text(encoding="utf-8")))
    except Exception:  # noqa: BLE001 - a stale artefact must not break the API
        return None
