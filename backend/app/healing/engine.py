"""Self-healing engine: executes remediation plans by changing the simulated network.

Every action mutates real simulator state (penalties, admin status, rate limits,
the routing table). Healed components are *quarantined*: they are excluded from
opening new incidents and are restored automatically once their telemetry has
been clean for a while, with a hold-down timer that grows if they flap.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.logging_config import get_logger
from app.models.detection import ComponentKind, DetectionResult
from app.models.diagnosis import ActionType, RemediationPlan
from app.models.incident import HealingActionRecord, RouteChange
from app.models.network import AdminStatus
from app.simulation.faults import FaultInjector
from app.simulation.network import NetworkSimulator
from app.simulation.routing import LinkMetricsInput
from app.telemetry.generator import TelemetryGenerator

log = get_logger("netmedic.healing")

RESTORE_CLEAN_TICKS = 6  # consecutive clean ticks before a quarantined component is restored
INITIAL_HOLD_TICKS = 10  # minimum quarantine length
FLAP_WINDOW_TICKS = 30  # re-triggering within this window after a restore counts as a flap
FLAP_HOLD_TICKS = 60  # hold-down applied after a flap


@dataclass
class Quarantine:
    component_id: str
    kind: ComponentKind
    action: ActionType
    incident_id: str
    applied_tick: int
    hold_ticks: int = INITIAL_HOLD_TICKS
    clean_ticks: int = 0
    rate_limited_flows: list[str] = field(default_factory=list)


@dataclass
class PendingRestart:
    node_id: str
    ticks_remaining: int
    incident_id: str


class HealingEngine:
    def __init__(self, network: NetworkSimulator, telemetry: TelemetryGenerator, faults: FaultInjector) -> None:
        self.network = network
        self.telemetry = telemetry
        self.faults = faults
        self.quarantines: dict[str, Quarantine] = {}
        self._restarts: dict[str, PendingRestart] = {}
        self._last_restored: dict[str, int] = {}  # component -> tick of last restore (flap detection)
        self.restored_events: list[tuple[str, str, str]] = []  # (incident_id, component_id, message) drained by the manager

    # ------------------------------------------------------------- queries
    def is_quarantined(self, component_id: str) -> bool:
        return component_id in self.quarantines

    def quarantined_ids(self) -> list[str]:
        return list(self.quarantines)

    # ------------------------------------------------------------- execute
    def execute(self, plan: RemediationPlan, incident_id: str, tick: int, snapshot_links) -> HealingActionRecord:
        record = HealingActionRecord(
            id=f"act-{uuid.uuid4().hex[:8]}",
            incident_id=incident_id,
            action=plan.action,
            target_id=plan.target_id,
            target_kind=plan.target_kind,
            parameters=dict(plan.parameters),
            started_at=datetime.now(timezone.utc),
            result="applied",
        )
        before = {fid: list(r.path) for fid, r in self.network.routes.items()}
        metrics = self._link_metrics(snapshot_links)
        limited_flows: list[str] = []
        try:
            if plan.action == ActionType.REROUTE_AROUND_NODE:
                penalty = float(plan.parameters.get("penalty_ms", 500.0))
                self.network.set_node_penalty(plan.target_id, penalty, isolated=True)
                self.network.recompute_routes(reason=f"avoid {plan.target_id}", link_metrics=metrics)
                record.details = f"Routing cost of {plan.target_id} raised by {penalty:.0f} ms; routes recomputed"
            elif plan.action == ActionType.REROUTE_AROUND_LINK:
                penalty = float(plan.parameters.get("penalty_ms", 500.0))
                self.network.set_link_penalty(plan.target_id, penalty, isolated=True)
                self.network.recompute_routes(reason=f"avoid {plan.target_id}", link_metrics=metrics)
                record.details = f"Routing cost of {plan.target_id} raised by {penalty:.0f} ms; routes recomputed"
            elif plan.action == ActionType.ISOLATE_LINK:
                self.network.set_link_penalty(plan.target_id, 1000.0, isolated=True)
                self.network.recompute_routes(reason=f"isolate {plan.target_id}", link_metrics=metrics)
                record.details = f"{plan.target_id} isolated from the forwarding table; routes recomputed"
            elif plan.action == ActionType.RESTART_NODE:
                ticks = int(plan.parameters.get("restart_ticks", 3))
                penalty = float(plan.parameters.get("penalty_ms", 500.0))
                self.network.set_node_penalty(plan.target_id, penalty, isolated=True)
                self.network.recompute_routes(reason=f"restart {plan.target_id}", link_metrics=metrics)
                self.network.set_node_status(plan.target_id, AdminStatus.DOWN)
                self._restarts[plan.target_id] = PendingRestart(plan.target_id, ticks, incident_id)
                record.details = f"Transit traffic moved off {plan.target_id}; service restarting (~{ticks} samples)"
            elif plan.action == ActionType.RATE_LIMIT_SOURCE:
                limit = float(plan.parameters.get("rate_limit_mbps", 300.0))
                for flow in self.network.flows.values():
                    if flow.source == plan.target_id:
                        self.network.set_flow_rate_limit(flow.id, limit)
                        limited_flows.append(flow.id)
                self.network.recompute_routes(reason=f"rebalance around {plan.target_id}", link_metrics=metrics)
                record.details = f"Flows {', '.join(limited_flows)} shaped to {limit:.0f} Mbps; uplinks rebalanced"
                record.parameters["flows"] = ",".join(limited_flows)
            else:
                record.result = "skipped"
                record.details = "No automatic action for this plan"
        except Exception as exc:  # noqa: BLE001
            log.exception("[HEALING] Action failed")
            record.result = "failed"
            record.details = str(exc)

        if record.result == "applied":
            after = {fid: list(r.path) for fid, r in self.network.routes.items()}
            record.route_changes = [
                RouteChange(flow_id=fid, before=before[fid], after=after[fid])
                for fid in before
                if before[fid] != after[fid]
            ]
            self.quarantines[plan.target_id] = Quarantine(
                component_id=plan.target_id,
                kind=plan.target_kind,
                action=plan.action,
                incident_id=incident_id,
                applied_tick=tick,
                hold_ticks=self._hold_for(plan.target_id, tick),
                rate_limited_flows=limited_flows,
            )
            for change in record.route_changes:
                log.info(
                    "[HEALING] %s rerouted %s -> %s",
                    change.flow_id,
                    " > ".join(change.before) or "-",
                    " > ".join(change.after) or "-",
                )
            log.info("[HEALING] %s on %s: %s", plan.action.value, plan.target_id, record.details)
        record.completed_at = datetime.now(timezone.utc)
        return record

    def _hold_for(self, component_id: str, tick: int) -> int:
        last = self._last_restored.get(component_id)
        if last is not None and tick - last <= FLAP_WINDOW_TICKS:
            log.info("[HEALING] %s is flapping; holding remediation for %d samples", component_id, FLAP_HOLD_TICKS)
            return FLAP_HOLD_TICKS
        return INITIAL_HOLD_TICKS

    # ------------------------------------------------------------ restore
    def restore(self, component_id: str, tick: int, reason: str = "telemetry back to normal") -> HealingActionRecord | None:
        q = self.quarantines.pop(component_id, None)
        if q is None:
            return None
        if q.kind == ComponentKind.NODE:
            self.network.set_node_penalty(component_id, 0.0, isolated=False)
        else:
            self.network.set_link_penalty(component_id, 0.0, isolated=False)
        for flow_id in q.rate_limited_flows:
            self.network.set_flow_rate_limit(flow_id, None)
        self.network.recompute_routes(reason="restore primary paths")
        self._last_restored[component_id] = tick
        message = f"{component_id} {reason}; primary routes restored"
        log.info("[HEALING] %s", message)
        self.restored_events.append((q.incident_id, component_id, message))
        return HealingActionRecord(
            id=f"act-{uuid.uuid4().hex[:8]}",
            incident_id=q.incident_id,
            action=q.action,
            target_id=component_id,
            target_kind=q.kind,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            result="restored",
            details=message,
        )

    def clear(self) -> None:
        self.quarantines.clear()
        self._restarts.clear()
        self._last_restored.clear()
        self.restored_events.clear()

    # --------------------------------------------------------------- tick
    def tick(self, tick: int, detection: DetectionResult | None) -> list[HealingActionRecord]:
        """Advance restarts and auto-restore quarantined components that stayed clean."""
        records: list[HealingActionRecord] = []
        for node_id, restart in list(self._restarts.items()):
            restart.ticks_remaining -= 1
            if restart.ticks_remaining <= 0:
                self.network.set_node_status(node_id, AdminStatus.UP)
                self.faults.on_node_restart(node_id)
                del self._restarts[node_id]
                log.info("[HEALING] %s back online after restart", node_id)

        flagged = {a.component_id for a in detection.anomalies} if detection else set()
        for component_id, q in list(self.quarantines.items()):
            if component_id in self._restarts:
                continue
            q.clean_ticks = q.clean_ticks + 1 if component_id not in flagged else 0
            if q.clean_ticks >= RESTORE_CLEAN_TICKS and tick - q.applied_tick >= q.hold_ticks:
                record = self.restore(component_id, tick)
                if record:
                    records.append(record)
        return records

    # ------------------------------------------------------------- helpers
    @staticmethod
    def _link_metrics(snapshot_links) -> dict[str, LinkMetricsInput]:
        return {
            l.link_id: LinkMetricsInput(utilization=l.utilization_percent / 100, packet_loss_percent=l.packet_loss_percent)
            for l in (snapshot_links or [])
        }
