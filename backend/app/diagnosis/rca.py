"""Root-cause analysis: score every (component, hypothesis) pair and explain the winner.

    score(H, C)  = weighted mean of rule strengths            (see rules.py)
    confidence   = best_score * (0.6 + 0.4 * (1 - second/best))

i.e. the confidence *is* the rule-match score, discounted by up to 40 % when a
competing hypothesis fits almost as well. Nothing here reads the fault injector.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.diagnosis.planner import build_plan
from app.diagnosis.rules import LINK_HYPOTHESES, NODE_HYPOTHESES, Context, node_failure, router_congestion, traffic_spike
from app.logging_config import get_logger
from app.models.detection import ComponentKind, DetectionResult
from app.models.diagnosis import ROOT_CAUSE_LABEL, Diagnosis, Hypothesis, RootCause
from app.models.network import NodeType
from app.models.telemetry import FlowStatus, TelemetrySnapshot
from app.simulation.network import NetworkSimulator

log = get_logger("netmedic.diagnosis")

MIN_SCORE = 0.35  # below this the best hypothesis is reported as UNKNOWN

METRIC_LABEL = {
    "latency_ms": ("Latency", " ms"),
    "packet_loss_percent": ("Packet loss", "%"),
    "throughput_mbps": ("Throughput", " Mbps"),
    "bandwidth_utilization_percent": ("Bandwidth utilisation", "%"),
    "cpu_percent": ("CPU", "%"),
    "memory_percent": ("Memory", "%"),
    "active_connections": ("Active connections", ""),
}
NEGATED_PREFIXES = ("not ", "no ")
NEGATED_SUFFIXES = (" normal", " healthy")

ROUTER_LIKE = {NodeType.ROUTER, NodeType.GATEWAY}


class RootCauseAnalyzer:
    def __init__(self, network: NetworkSimulator) -> None:
        self.network = network

    def diagnose(
        self, detection: DetectionResult, snapshot: TelemetrySnapshot, exclude: set[str] | None = None
    ) -> Diagnosis | None:
        """Diagnose the flagged components. `exclude` holds components already under remediation."""
        exclude = exclude or set()
        candidates = [
            a
            for a in detection.anomalies
            if a.component_kind in (ComponentKind.NODE, ComponentKind.LINK) and a.component_id not in exclude
        ]
        if not candidates:
            return None
        ctx = Context(self.network, snapshot)

        hypotheses: list[Hypothesis] = []
        for anomaly in candidates:
            if anomaly.component_kind == ComponentKind.NODE:
                node_type = self.network.nodes[anomaly.component_id].type
                for rule in NODE_HYPOTHESES:
                    if rule is router_congestion and node_type not in ROUTER_LIKE:
                        continue
                    if rule is traffic_spike and node_type != NodeType.SWITCH:
                        continue
                    if rule is node_failure and snapshot.node(anomaly.component_id).status.value == "up":
                        continue
                    hypotheses.append(rule(ctx, anomaly.component_id))
            else:
                for rule in LINK_HYPOTHESES:
                    hypotheses.append(rule(ctx, anomaly.component_id))

        hypotheses.sort(key=lambda h: h.score, reverse=True)
        best = hypotheses[0]
        second = hypotheses[1].score if len(hypotheses) > 1 else 0.0
        if best.score < MIN_SCORE:
            root_cause = RootCause.UNKNOWN
            confidence = round(best.score * 0.5, 3)
            explanation = f"Best hypothesis ({ROOT_CAUSE_LABEL[best.root_cause]} on {best.target_id}) only scored {best.score:.2f}; below the {MIN_SCORE:.2f} threshold."
        else:
            root_cause = best.root_cause
            margin_factor = 1 - (second / best.score if best.score else 0)
            confidence = round(best.score * (0.6 + 0.4 * margin_factor), 3)
            explanation = (
                f"Rule-match score {best.score:.2f} for {ROOT_CAUSE_LABEL[root_cause]} on {best.target_id}; "
                f"runner-up scored {second:.2f}, so confidence = {best.score:.2f} x (0.6 + 0.4 x {margin_factor:.2f}) = {confidence:.2f}."
            )

        affected_flows = self._affected_flows(best, snapshot)
        anomaly = detection.anomaly(best.target_id)
        evidence = self._evidence(best, ctx, affected_flows, anomaly.deviations if anomaly else [])
        plan = build_plan(root_cause, best.target_id, best.target_kind, self.network, affected_flows)

        log.info(
            "[DIAGNOSIS] Likely root cause: %s on %s (confidence %.0f%%)",
            root_cause.value,
            best.target_id,
            confidence * 100,
        )
        return Diagnosis(
            tick=detection.tick,
            timestamp=datetime.now(timezone.utc),
            root_cause=root_cause,
            root_cause_label=ROOT_CAUSE_LABEL[root_cause],
            target_id=best.target_id,
            target_kind=best.target_kind,
            confidence=confidence,
            confidence_explanation=explanation,
            evidence=evidence,
            affected_flows=affected_flows,
            affected_components=[a.component_id for a in detection.anomalies],
            hypotheses=hypotheses[:8],
            anomaly_severity=anomaly.severity if anomaly else 0.0,
            plan=plan,
        )

    # ------------------------------------------------------------ helpers
    def _affected_flows(self, best: Hypothesis, snapshot: TelemetrySnapshot) -> list[str]:
        flows = []
        for f in snapshot.flows:
            on_path = best.target_id in f.path if best.target_kind == ComponentKind.NODE else best.target_id in f.links
            if on_path and (f.status != FlowStatus.OK):
                flows.append(f.flow_id)
        if flows:
            return flows
        # Fall back to every flow using the component (e.g. the impact is not yet visible end-to-end).
        return [
            f.flow_id
            for f in snapshot.flows
            if (best.target_id in f.path if best.target_kind == ComponentKind.NODE else best.target_id in f.links)
        ]

    def _evidence(self, best: Hypothesis, ctx: Context, affected_flows: list[str], deviations) -> list[str]:
        lines: list[str] = []
        # 1. What changed versus the component's own healthy baseline (from detection).
        covered: set[str] = set()
        for d in deviations[:4]:
            label, unit = METRIC_LABEL.get(d.metric, (d.metric, d.unit))
            verb = "increased" if d.direction == "up" else "dropped"
            lines.append(f"{label} {verb} from {d.baseline:.1f}{unit} to {d.current:.1f}{unit} ({d.ratio:.1f}x)")
            covered.add(label.split()[0].lower())
        # 2. Strong positive symptoms not already covered (negated / "normal" checks are context, not evidence).
        for c in best.checks:
            cond = c.condition.lower()
            if c.strength < 0.5 or cond.startswith(NEGATED_PREFIXES) or cond.endswith(NEGATED_SUFFIXES):
                continue
            key = cond.split()[0]
            if key in covered or key == "neighbours":
                continue
            covered.add(key)
            lines.append(f"{c.condition[0].upper()}{c.condition[1:]}: {c.observation}")
        # 3. Neighbour context.
        if best.target_kind == ComponentKind.NODE:
            neighbours = ctx.neighbour_nodes(best.target_id)
            healthy = [n.node_id for n in neighbours if n.health_score >= 85]
            degraded = [n.node_id for n in neighbours if n.health_score < 85]
            if healthy and not degraded:
                lines.append(f"Neighbouring nodes {', '.join(healthy)} remain healthy")
            elif degraded:
                lines.append(f"Neighbouring nodes also degraded: {', '.join(degraded)}")
        else:
            link = ctx.link(best.target_id)
            a, b = ctx.node(link.source), ctx.node(link.target)
            lines.append(f"Endpoints {a.node_id} ({a.health.value}) and {b.node_id} ({b.health.value})")
        # 4. Impact.
        if affected_flows:
            lines.append(f"Flows {', '.join(affected_flows)} traverse {best.target_id} and are impacted ({len(affected_flows)} of {len(ctx.snapshot.flows)})")
        return lines[:8]
