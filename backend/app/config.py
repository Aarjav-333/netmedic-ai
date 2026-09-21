"""Application configuration loaded from environment variables / .env."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    """Runtime settings. Every value can be overridden with a NETMEDIC_* env var."""

    model_config = SettingsConfigDict(
        env_prefix="NETMEDIC_",
        env_file=(REPO_DIR / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"

    # Simulation loop
    tick_seconds: float = Field(default=1.5, ge=0.2, le=10.0)
    # Disable the background loop (tests drive the engine tick-by-tick).
    auto_tick: bool = True

    # Persistence
    database_url: str = "sqlite:///./data/netmedic.db"

    # CORS
    cors_origins: str = "http://localhost:3000"

    # AI explanation provider
    ai_provider: Literal["mock", "qualcomm"] = "mock"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


class QualcommSettings(BaseSettings):
    """Qualcomm Cloud AI Playground connection details.

    Nothing here is hardcoded - every value must be provided by the operator
    from the Qualcomm platform. If any required value is missing the system
    falls back to the MockProvider.
    """

    model_config = SettingsConfigDict(
        env_prefix="QUALCOMM_AI_",
        env_file=(REPO_DIR / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    base_url: str = ""
    api_key: str = ""
    model: str = ""
    timeout_seconds: float = 20.0

    @property
    def is_configured(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_qualcomm_settings() -> QualcommSettings:
    return QualcommSettings()
