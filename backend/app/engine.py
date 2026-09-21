"""SimulationEngine: the single orchestrator that owns every pipeline stage.

Phase 1 exposes the network simulator only. Later phases plug telemetry,
detection, diagnosis, healing and verification into the tick loop here.
"""

from __future__ import annotations

from functools import lru_cache

from app.logging_config import get_logger
from app.simulation.network import NetworkSimulator

log = get_logger("netmedic.engine")


class SimulationEngine:
    def __init__(self) -> None:
        self.network = NetworkSimulator()
        self.tick_count = 0

    def reset(self) -> None:
        self.network.reset()
        self.tick_count = 0
        log.info("[ENGINE] Reset to healthy baseline")


@lru_cache
def get_engine() -> SimulationEngine:
    return SimulationEngine()
