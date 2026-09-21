"""NetMedic AI backend entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.detection import router as detection_router
from app.api.diagnosis import router as diagnosis_router
from app.api.faults import router as faults_router
from app.api.health import router as health_router
from app.api.network import router as network_router
from app.api.telemetry import router as telemetry_router
from app.api.ws import manager as ws_manager
from app.api.ws import router as ws_router
from app.config import get_settings
from app.engine import get_engine
from app.logging_config import configure_logging, get_logger

log = get_logger("netmedic")

APP_VERSION = "0.5.0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    log.info("[STARTUP] NetMedic AI backend v%s starting (tick=%ss)", APP_VERSION, settings.tick_seconds)
    engine = get_engine()
    engine.subscribe(ws_manager.broadcast)
    if settings.auto_tick:
        await engine.start()
    yield
    await engine.stop()
    log.info("[SHUTDOWN] NetMedic AI backend stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="NetMedic AI",
        description="Autonomous Network Detection, Diagnosis & Self-Healing Platform",
        version=APP_VERSION,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router, prefix="/api")
    app.include_router(network_router, prefix="/api")
    app.include_router(telemetry_router, prefix="/api")
    app.include_router(faults_router, prefix="/api")
    app.include_router(detection_router, prefix="/api")
    app.include_router(diagnosis_router, prefix="/api")
    app.include_router(ws_router)
    return app


app = create_app()
