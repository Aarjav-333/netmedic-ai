"""NetMedic AI backend entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.config import get_settings
from app.logging_config import configure_logging, get_logger

log = get_logger("netmedic")

APP_VERSION = "0.1.0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    log.info("[STARTUP] NetMedic AI backend v%s starting (tick=%ss)", APP_VERSION, settings.tick_seconds)
    yield
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
    return app


app = create_app()
