"""Fault injector: applies faults to the simulation as *physical effects*.

Ground truth (which fault was injected where) is stored here for the operator
UI and for evaluation only. Detection and root-cause analysis never read it -
they work from telemetry and topology alone.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from app.logging_config import get_logger
from app.models.faults import ActiveFaultSchema, FaultDefinition, FaultType, Severity, TargetKind
from app.models.network import AdminStatus, NodeType
from app.simulation.effects import FlowEffects, LinkEffects, NodeEffects, SimulationEffects
from app.simulation.network import NetworkSimulator

log = get_logger("netmedic.faults")

FAULT_CATALOG: tuple[FaultDefinition, ...] = (
    FaultDefinition(
        type=FaultType.ROUTER_CONGESTION,
        label="Router congestion",
        description="A burst of traffic saturates the router: utilisation, CPU, latency and loss climb.",
        target_kind=TargetKind.NODE,
        node_types=[NodeType.ROUTER.value, NodeType.GATEWAY.value],
    ),
    FaultDefinition(
        type=FaultType.LINK_FAILURE,
        label="Link failure",
        description="The link goes down; every flow routed over it is cut until traffic is rerouted.",
        target_kind=TargetKind.LINK,
    ),
    FaultDefinition(
        type=FaultType.PACKET_LOSS_SPIKE,
        label="Packet-loss spike",
        description="The link starts dropping packets (faulty optics / interference).",
        target_kind=TargetKind.LINK,
    ),
    FaultDefinition(
        type=FaultType.BANDWIDTH_DEGRADATION,
        label="Bandwidth degradation",
        description="Effective link capacity collapses; traffic queues and overflows.",
        target_kind=TargetKind.LINK,
    ),
    FaultDefinition(
        type=FaultType.NODE_OVERLOAD,
        label="Node overload (CPU / memory)",
        description="A runaway process pins CPU and memory while the links stay healthy.",
        target_kind=TargetKind.NODE,
        node_types=[NodeType.ROUTER.value, NodeType.SWITCH.value, NodeType.SERVER.value, NodeType.GATEWAY.value],
    ),
    FaultDefinition(
        type=FaultType.TRAFFIC_SPIKE,
        label="Traffic spike",
        description="Demand from the access switch multiplies, saturating it and its uplink.",
        target_kind=TargetKind.NODE,
        node_types=[NodeType.SWITCH.value],
    ),
    FaultDefinition(
        type=FaultType.ROUTER_FAILURE,
        label="Complete router failure",
        description="The node goes offline; all traffic through it is lost until rerouted.",
        target_kind=TargetKind.NODE,
        node_types=[NodeType.ROUTER.value, NodeType.SWITCH.value],
    ),
)
CATALOG_BY_TYPE = {d.type: d for d in FAULT_CATALOG}

# Severity scaling. Fractions are of the target's capacity where relevant.
CONGESTION_LOAD_FRACTION = {Severity.LOW: 0.55, Severity.MEDIUM: 0.75, Severity.HIGH: 0.95}
CONGESTION_CPU_ADD = {Severity.LOW: 15.0, Severity.MEDIUM: 25.0, Severity.HIGH: 35.0}
OVERLOAD_CPU_ADD = {Severity.LOW: 45.0, Severity.MEDIUM: 60.0, Severity.HIGH: 75.0}
OVERLOAD_MEM_ADD = {Severity.LOW: 30.0, Severity.MEDIUM: 40.0, Severity.HIGH: 50.0}
OVERLOAD_LATENCY_ADD = {Severity.LOW: 12.0, Severity.MEDIUM: 28.0, Severity.HIGH: 45.0}
OVERLOAD_LOSS_ADD = {Severity.LOW: 0.4, Severity.MEDIUM: 1.2, Severity.HIGH: 2.5}
LOSS_SPIKE_ADD = {Severity.LOW: 4.0, Severity.MEDIUM: 10.0, Severity.HIGH: 20.0}
BANDWIDTH_MULTIPLIER = {Severity.LOW: 0.6, Severity.MEDIUM: 0.45, Severity.HIGH: 0.3}
TRAFFIC_MULTIPLIER = {Severity.LOW: 2.0, Severity.MEDIUM: 3.0, Severity.HIGH: 4.0}


@dataclass
class ActiveFault:
    id: str
    type: FaultType
    target_id: str
    target_kind: TargetKind
    severity: Severity
    injected_at: datetime
    expires_at: datetime | None = None
    cleared_at: datetime | None = None
    cleared_by: str | None = None
    restore: dict[str, AdminStatus] = field(default_factory=dict)  # admin statuses to restore on clear

    @property
    def is_active(self) -> bool:
        return self.cleared_at is None

    def to_schema(self) -> ActiveFaultSchema:
        return ActiveFaultSchema(
            id=self.id,
            type=self.type,
            label=CATALOG_BY_TYPE[self.type].label,
            target_id=self.target_id,
            target_kind=self.target_kind,
            severity=self.severity,
            injected_at=self.injected_at,
            expires_at=self.expires_at,
            cleared_at=self.cleared_at,
            cleared_by=self.cleared_by,
        )


class FaultInjectionError(ValueError):
    """Raised for invalid fault/target combinations."""


class FaultInjector:
    def __init__(self, network: NetworkSimulator) -> None:
        self.network = network
        self._faults: dict[str, ActiveFault] = {}

    # ------------------------------------------------------------ queries
    @property
    def active(self) -> list[ActiveFault]:
        return [f for f in self._faults.values() if f.is_active]

    def all_faults(self) -> list[ActiveFault]:
        return list(self._faults.values())

    def get(self, fault_id: str) -> ActiveFault | None:
        return self._faults.get(fault_id)

    def ground_truth(self) -> list[tuple[FaultType, str]]:
        """(fault type, target) pairs of active faults - evaluation/debug only."""
        return [(f.type, f.target_id) for f in self.active]

    # ------------------------------------------------------------- inject
    def inject(
        self,
        fault_type: FaultType,
        target_id: str,
        severity: Severity = Severity.MEDIUM,
        duration_seconds: float | None = None,
    ) -> ActiveFault:
        definition = CATALOG_BY_TYPE[fault_type]
        self._validate_target(definition, target_id)
        now = datetime.now(timezone.utc)
        fault = ActiveFault(
            id=f"fault-{uuid.uuid4().hex[:8]}",
            type=fault_type,
            target_id=target_id,
            target_kind=definition.target_kind,
            severity=severity,
            injected_at=now,
            expires_at=now + timedelta(seconds=duration_seconds) if duration_seconds else None,
        )
        self._apply_admin_changes(fault)
        self._faults[fault.id] = fault
        log.info("[FAULT] Injected %s on %s (severity=%s)", fault_type.value, target_id, severity.value)
        return fault

    def _validate_target(self, definition: FaultDefinition, target_id: str) -> None:
        if definition.target_kind == TargetKind.LINK:
            if target_id not in self.network.links:
                raise FaultInjectionError(f"{definition.label} requires a link target; unknown link {target_id!r}")
            return
        node = self.network.nodes.get(target_id)
        if node is None:
            raise FaultInjectionError(f"{definition.label} requires a node target; unknown node {target_id!r}")
        if definition.node_types and node.type.value not in definition.node_types:
            allowed = ", ".join(definition.node_types)
            raise FaultInjectionError(f"{definition.label} can only target: {allowed} (got {node.type.value})")
        if any(f.target_id == target_id and f.type == definition.type for f in self.active):
            raise FaultInjectionError(f"{definition.label} is already active on {target_id}")

    def _apply_admin_changes(self, fault: ActiveFault) -> None:
        if fault.type == FaultType.LINK_FAILURE:
            link = self.network.links[fault.target_id]
            fault.restore[fault.target_id] = link.status
            self.network.set_link_status(fault.target_id, AdminStatus.DOWN)
        elif fault.type == FaultType.ROUTER_FAILURE:
            node = self.network.nodes[fault.target_id]
            fault.restore[fault.target_id] = node.status
            self.network.set_node_status(fault.target_id, AdminStatus.DOWN)

    # -------------------------------------------------------------- clear
    def clear(self, fault_id: str, reason: str = "reset") -> ActiveFault | None:
        fault = self._faults.get(fault_id)
        if fault is None or not fault.is_active:
            return None
        for target, status in fault.restore.items():
            if fault.target_kind == TargetKind.LINK:
                self.network.set_link_status(target, status)
            else:
                self.network.set_node_status(target, status)
        fault.cleared_at = datetime.now(timezone.utc)
        fault.cleared_by = reason
        log.info("[FAULT] Cleared %s on %s (%s)", fault.type.value, fault.target_id, reason)
        return fault

    def clear_all(self, reason: str = "reset") -> int:
        cleared = 0
        for fault in self.active:
            if self.clear(fault.id, reason):
                cleared += 1
        return cleared

    def forget_cleared(self, keep_last: int = 20) -> None:
        cleared = [f for f in self._faults.values() if not f.is_active]
        for fault in cleared[:-keep_last]:
            del self._faults[fault.id]

    def expire(self, now: datetime | None = None) -> list[ActiveFault]:
        now = now or datetime.now(timezone.utc)
        expired = [f for f in self.active if f.expires_at and f.expires_at <= now]
        for fault in expired:
            self.clear(fault.id, reason="expired")
        return expired

    # ------------------------------------------------------------ effects
    def effects(self) -> SimulationEffects:
        """Translate active faults into physical effects for the telemetry generator."""
        fx = SimulationEffects()
        for fault in self.active:
            sev = fault.severity
            if fault.type == FaultType.ROUTER_CONGESTION:
                node = self.network.nodes[fault.target_id]
                fx.add_node(
                    fault.target_id,
                    NodeEffects(
                        extra_load_mbps=node.capacity_mbps * CONGESTION_LOAD_FRACTION[sev],
                        cpu_add_percent=CONGESTION_CPU_ADD[sev],
                        memory_add_percent=CONGESTION_CPU_ADD[sev] * 0.4,
                        connections_multiplier=1.6,
                    ),
                )
            elif fault.type == FaultType.NODE_OVERLOAD:
                fx.add_node(
                    fault.target_id,
                    NodeEffects(
                        cpu_add_percent=OVERLOAD_CPU_ADD[sev],
                        memory_add_percent=OVERLOAD_MEM_ADD[sev],
                        latency_add_ms=OVERLOAD_LATENCY_ADD[sev],
                        packet_loss_add_percent=OVERLOAD_LOSS_ADD[sev],
                    ),
                )
            elif fault.type == FaultType.PACKET_LOSS_SPIKE:
                fx.add_link(fault.target_id, LinkEffects(packet_loss_add_percent=LOSS_SPIKE_ADD[sev], latency_add_ms=2.0))
            elif fault.type == FaultType.BANDWIDTH_DEGRADATION:
                fx.add_link(fault.target_id, LinkEffects(capacity_multiplier=BANDWIDTH_MULTIPLIER[sev]))
            elif fault.type == FaultType.TRAFFIC_SPIKE:
                for flow in self.network.flows.values():
                    if flow.source == fault.target_id:
                        fx.add_flow(flow.id, FlowEffects(demand_multiplier=TRAFFIC_MULTIPLIER[sev]))
                fx.add_node(fault.target_id, NodeEffects(connections_multiplier=TRAFFIC_MULTIPLIER[sev]))
            # LINK_FAILURE / ROUTER_FAILURE act through admin status, not effects.
        return fx

    def reset(self) -> int:
        cleared = self.clear_all(reason="reset")
        self._faults.clear()
        return cleared
