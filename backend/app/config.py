"""Application configuration loaded from environment variables / .env."""

from __future__ import annotations

import re
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

    # Telemetry RNG seed. Unset in production so each run looks different; the test suite
    # pins it so detection assertions ("no false positives") are reproducible rather than
    # a dice roll on the noise draw.
    random_seed: int | None = None

    # Persistence
    database_url: str = "sqlite:///./data/netmedic.db"

    # CORS. The API has no authentication, so any allowed origin can both read telemetry
    # and drive the simulation (inject faults, reset, toggle healing). Keep the allow-list
    # as narrow as the demo needs: exact origins by default, plus an optional full-matched
    # regex for LAN demos. Never widen the regex to `^https?://[^/]+:<port>` - that lets any
    # site served on that port drive this API from a victim's browser.
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000,http://[::1]:3000"
    cors_origin_regex: str | None = None

    # AI explanation provider
    ai_provider: Literal["mock", "qualcomm"] = "mock"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def is_allowed_origin(self, origin: str) -> bool:
        """Same rule the CORS middleware applies, reused for the WebSocket handshake."""
        if "*" in self.cors_origin_list or origin in self.cors_origin_list:
            return True
        if self.cors_origin_regex:
            return re.fullmatch(self.cors_origin_regex, origin) is not None
        return False


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
def _load_settings() -> Settings:
    return Settings()


_settings_override: Settings | None = None


def get_settings() -> Settings:
    """Process settings: an explicit override if one is installed, else the environment."""
    return _settings_override if _settings_override is not None else _load_settings()


def configure_settings(settings: Settings | None) -> Settings | None:
    """Install process-wide settings and return the previous override so callers can restore.

    `create_app(settings)` uses this so components resolved *afterwards* (the engine, the AI
    provider) agree with the app's own config. A component already constructed keeps the
    settings it was built with - `get_engine()` is an lru_cache singleton.
    """
    global _settings_override
    previous = _settings_override
    _settings_override = settings
    return previous


@lru_cache
def get_qualcomm_settings() -> QualcommSettings:
    return QualcommSettings()
