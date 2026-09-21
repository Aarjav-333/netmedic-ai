"""Shared pytest fixtures."""

from __future__ import annotations

import os

# Tests drive the engine explicitly; never let the background loop interfere.
os.environ.setdefault("NETMEDIC_AUTO_TICK", "false")
os.environ.setdefault("NETMEDIC_DATABASE_URL", "sqlite:///./data/netmedic_test.db")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.engine import SimulationEngine, get_engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


@pytest.fixture
def engine() -> SimulationEngine:
    eng = get_engine()
    eng.reset()
    return eng
