"""Demo mode: a scripted *scenario* that drives the real pipeline.

The runner only resets the simulation, waits, and injects a fault - detection,
diagnosis, healing and verification are the same code paths a manual injection
triggers. Nothing in the outcome is predetermined.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from app.logging_config import get_logger
from app.models.faults import FaultType, InjectFaultRequest, Severity
from app.models.incident import OPEN_STATUSES

if TYPE_CHECKING:
    from app.engine import SimulationEngine

log = get_logger("netmedic.demo")


@dataclass(frozen=True)
class Scenario:
    key: str
    title: str
    description: str
    fault_type: FaultType
    target_id: str
    severity: Severity


SCENARIOS: dict[str, Scenario] = {
    s.key: s
    for s in (
        Scenario(
            "congestion",
            "Router congestion on R4",
            "Hostel router saturates; traffic is rerouted through R3 and recovery is verified.",
            FaultType.ROUTER_CONGESTION,
            "R4",
            Severity.MEDIUM,
        ),
        Scenario(
            "link_failure",
            "Link failure R4-SW3",
            "The hostel uplink goes down; the failed link is isolated and flows move to the backup uplink.",
            FaultType.LINK_FAILURE,
            "L-R4-SW3",
            Severity.MEDIUM,
        ),
        Scenario(
            "traffic_spike",
            "Traffic spike at SW3",
            "Hostel demand triples; the source is rate-limited and uplinks rebalanced.",
            FaultType.TRAFFIC_SPIKE,
            "SW3",
            Severity.MEDIUM,
        ),
        Scenario(
            "overload",
            "Node overload on R2",
            "A runaway process pins R2's CPU; the node is restarted while traffic is rerouted.",
            FaultType.NODE_OVERLOAD,
            "R2",
            Severity.HIGH,
        ),
    )
}

HEALTHY_PAUSE_SECONDS = 5.0
PIPELINE_TIMEOUT_SECONDS = 60.0


@dataclass
class DemoState:
    running: bool = False
    scenario: str | None = None
    step: int = 0
    total_steps: int = 5
    message: str = "Idle"
    started_at: datetime | None = None
    finished_at: datetime | None = None
    outcome: str | None = None
    incident_id: str | None = None
    history: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "scenario": self.scenario,
            "step": self.step,
            "total_steps": self.total_steps,
            "message": self.message,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "outcome": self.outcome,
            "incident_id": self.incident_id,
            "history": list(self.history),
        }


class DemoRunner:
    def __init__(self, engine: "SimulationEngine") -> None:
        self.engine = engine
        self.state = DemoState()
        self._task: asyncio.Task[None] | None = None

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self, scenario_key: str = "congestion") -> DemoState:
        if scenario_key not in SCENARIOS:
            raise KeyError(scenario_key)
        if self.is_running:
            raise RuntimeError("A demo is already running")
        scenario = SCENARIOS[scenario_key]
        self.state = DemoState(running=True, scenario=scenario.key, started_at=datetime.now(timezone.utc))
        self._task = asyncio.create_task(self._run(scenario), name="netmedic-demo")
        return self.state

    async def stop(self) -> DemoState:
        if self.is_running and self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self.state.running:
            await self._finish("Demo stopped by operator", outcome="stopped")
        return self.state

    async def _step(self, step: int, message: str) -> None:
        self.state.step = step
        self.state.message = message
        self.state.history.append(message)
        log.info("[DEMO] Step %d/%d - %s", step, self.state.total_steps, message)
        await self.engine.publish()

    async def _finish(self, message: str, outcome: str) -> None:
        self.state.running = False
        self.state.message = message
        self.state.outcome = outcome
        self.state.finished_at = datetime.now(timezone.utc)
        self.state.history.append(message)
        log.info("[DEMO] %s", message)
        await self.engine.publish()

    async def _run(self, scenario: Scenario) -> None:
        try:
            await self._step(1, "Resetting the simulation to a healthy baseline")
            await self.engine.reset_async()
            self.engine.incidents.auto_heal = True

            await self._step(2, f"Observing the healthy network for {HEALTHY_PAUSE_SECONDS:.0f} s")
            await asyncio.sleep(HEALTHY_PAUSE_SECONDS)

            await self._step(3, f"Injecting {scenario.title.lower()} ({scenario.severity.value} severity)")
            await self.engine.inject_fault(
                InjectFaultRequest(fault_type=scenario.fault_type, target_id=scenario.target_id, severity=scenario.severity)
            )

            await self._step(4, "Pipeline running: detect -> diagnose -> heal -> verify")
            incident_id = await self._wait_for_incident()
            if incident_id is None:
                await self._finish("Demo ended: the pipeline did not close an incident in time", outcome="timeout")
                return
            incident = self.engine.incidents.get(incident_id)
            status = incident.status.value if incident else "unknown"
            self.state.incident_id = incident_id
            await self._step(5, f"Incident {incident_id} closed as {status.upper().replace('_', ' ')}")
            await self._finish(
                f"Demo complete - {scenario.title}: {status.replace('_', ' ')}. The fault stays active so the reroute remains visible; press Reset to restore.",
                outcome=status,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            log.exception("[DEMO] Failed")
            await self._finish(f"Demo failed: {exc}", outcome="error")

    async def _wait_for_incident(self) -> str | None:
        deadline = asyncio.get_running_loop().time() + PIPELINE_TIMEOUT_SECONDS
        seen: str | None = None
        while asyncio.get_running_loop().time() < deadline:
            active = self.engine.incidents.active
            if active is not None:
                seen = active.id
            elif seen is not None:
                closed = self.engine.incidents.get(seen)
                if closed is not None and closed.status not in OPEN_STATUSES:
                    return seen
            await asyncio.sleep(0.5)
        return None
