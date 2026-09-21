"""SimulationEngine: the single orchestrator that owns every pipeline stage.

One background asyncio task calls `tick()` every `tick_seconds`. Each tick runs
the pipeline in a fixed order (telemetry -> detection -> diagnosis -> healing ->
verification, later phases plug in here) and then publishes a state message to
every subscriber (the WebSocket manager).
"""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Awaitable, Callable
from functools import lru_cache
from typing import Any

from app.config import get_settings
from app.detection.detector import AnomalyDetector
from app.diagnosis.rca import RootCauseAnalyzer
from app.healing.engine import HealingEngine
from app.incidents.manager import IncidentManager
from app.logging_config import get_logger
from app.models.detection import DetectionResult
from app.models.diagnosis import Diagnosis
from app.models.faults import InjectFaultRequest
from app.models.incident import Incident
from app.models.telemetry import MetricPoint, TelemetrySnapshot
from app.simulation.effects import SimulationEffects
from app.simulation.faults import ActiveFault, FaultInjector
from app.simulation.network import NetworkSimulator
from app.telemetry.generator import TelemetryGenerator

log = get_logger("netmedic.engine")

HISTORY_LENGTH = 240  # ticks kept in memory for charts / verification windows

StateListener = Callable[[dict[str, Any]], Awaitable[None]]


class SimulationEngine:
    def __init__(self, tick_seconds: float = 1.5) -> None:
        self.tick_seconds = tick_seconds
        self.network = NetworkSimulator()
        self.telemetry = TelemetryGenerator(self.network)
        self.faults = FaultInjector(self.network)
        self.detector = AnomalyDetector(self.network)
        self.detection: DetectionResult | None = None
        self.rca = RootCauseAnalyzer(self.network)
        self.diagnosis: Diagnosis | None = None
        self.effects = SimulationEffects()
        self.history: deque[TelemetrySnapshot] = deque(maxlen=HISTORY_LENGTH)
        self.healing = HealingEngine(self.network, self.telemetry, self.faults)
        self.incidents = IncidentManager(self.healing, self.history, auto_heal=True)
        self.latest: TelemetrySnapshot | None = None
        self.tick_count = 0
        self._listeners: list[StateListener] = []
        self._task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()

    # ----------------------------------------------------------- lifecycle
    async def start(self) -> None:
        if self._task is not None:
            return
        self.tick()  # make state available immediately
        self._task = asyncio.create_task(self._run_loop(), name="netmedic-tick-loop")
        log.info("[ENGINE] Tick loop started (%.1fs)", self.tick_seconds)

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None
        log.info("[ENGINE] Tick loop stopped")

    async def _run_loop(self) -> None:
        while True:
            await asyncio.sleep(self.tick_seconds)
            try:
                async with self._lock:
                    self.tick()
                await self.publish()
            except Exception:  # noqa: BLE001 - never let the loop die
                log.exception("[ENGINE] Tick failed")

    # ---------------------------------------------------------------- tick
    def tick(self) -> TelemetrySnapshot:
        """Run one pipeline iteration synchronously (used by the loop and by tests)."""
        self.tick_count += 1
        self.faults.expire()
        for record in self.healing.tick(self.tick_count, self.detection):
            self.incidents.record_action(record)
        self.effects = self.faults.effects()
        snapshot = self.telemetry.generate(self.tick_count, self.effects)
        self.history.append(snapshot)
        self.latest = snapshot
        self.detection = self.detector.detect(snapshot)
        quarantined = set(self.healing.quarantined_ids())
        self.diagnosis = (
            self.rca.diagnose(self.detection, snapshot, exclude=quarantined) if self.detection.anomalies else None
        )
        self.incidents.process(self.tick_count, snapshot, self.detection, self.diagnosis)
        return snapshot

    def reset(self) -> int:
        self.incidents.cancel_active(self.tick_count, "Simulation reset by operator")
        self.incidents.reset()
        self.healing.clear()
        cleared = self.faults.reset()
        self.network.reset()
        self.effects = SimulationEffects()
        self.telemetry.reset_noise()
        self.detector.reset()
        self.detection = None
        self.diagnosis = None
        self.history.clear()
        self.tick_count = 0
        self.latest = None
        self.tick()
        log.info("[ENGINE] Reset to healthy baseline (%d faults cleared)", cleared)
        return cleared

    async def reset_async(self) -> int:
        async with self._lock:
            cleared = self.reset()
        await self.publish()
        return cleared

    # ------------------------------------------------------------- faults
    async def inject_fault(self, request: InjectFaultRequest) -> ActiveFault:
        async with self._lock:
            fault = self.faults.inject(
                request.fault_type, request.target_id, request.severity, request.duration_seconds
            )
            self.tick()  # reflect the fault immediately instead of waiting for the next tick
        await self.publish()
        return fault

    # ------------------------------------------------------------ healing
    async def execute_healing(self, incident_id: str) -> Incident:
        async with self._lock:
            incident = self.incidents.request_healing(incident_id)
            self.tick()  # run the REMEDIATING stage right away
        await self.publish()
        return incident

    async def set_auto_heal(self, enabled: bool) -> bool:
        async with self._lock:
            self.incidents.auto_heal = enabled
        await self.publish()
        return enabled

    async def clear_fault(self, fault_id: str) -> ActiveFault | None:
        async with self._lock:
            fault = self.faults.clear(fault_id, reason="operator")
            if fault is not None:
                self.tick()
        if fault is not None:
            await self.publish()
        return fault

    # ----------------------------------------------------------- publish
    def subscribe(self, listener: StateListener) -> None:
        self._listeners.append(listener)

    def state_message(self) -> dict[str, Any]:
        """Everything the dashboard needs, serialised as JSON-ready primitives."""
        return {
            "type": "state",
            "tick": self.tick_count,
            "topology": self.network.to_topology_response().model_dump(mode="json"),
            "telemetry": self.latest.model_dump(mode="json") if self.latest else None,
            "faults": [f.to_schema().model_dump(mode="json") for f in self.faults.active],
            "detection": self.detection.model_dump(mode="json") if self.detection else None,
            "diagnosis": self.diagnosis.model_dump(mode="json") if self.diagnosis else None,
            "incident": self.incidents.active.model_dump(mode="json") if self.incidents.active else None,
            "incidents": [s.model_dump(mode="json") for s in self.incidents.summaries()[:25]],
            "quarantined": self.healing.quarantined_ids(),
            "auto_heal": self.incidents.auto_heal,
        }

    async def publish(self) -> None:
        if not self._listeners:
            return
        message = self.state_message()
        for listener in list(self._listeners):
            try:
                await listener(message)
            except Exception:  # noqa: BLE001
                log.exception("[ENGINE] Listener failed")

    # ------------------------------------------------------------ history
    def metric_points(self, limit: int = 120) -> list[MetricPoint]:
        points: list[MetricPoint] = []
        for snap in list(self.history)[-limit:]:
            points.append(
                MetricPoint(
                    tick=snap.tick,
                    timestamp=snap.timestamp,
                    health_score=snap.summary.health_score,
                    avg_latency_ms=snap.summary.avg_latency_ms,
                    avg_packet_loss_percent=snap.summary.avg_packet_loss_percent,
                    total_throughput_mbps=snap.summary.total_throughput_mbps,
                    node_latency_ms={n.node_id: n.latency_ms for n in snap.nodes},
                    node_cpu_percent={n.node_id: n.cpu_percent for n in snap.nodes},
                    node_utilization_percent={n.node_id: n.bandwidth_utilization_percent for n in snap.nodes},
                    node_packet_loss_percent={n.node_id: n.packet_loss_percent for n in snap.nodes},
                )
            )
        return points


@lru_cache
def get_engine() -> SimulationEngine:
    return SimulationEngine(tick_seconds=get_settings().tick_seconds)
