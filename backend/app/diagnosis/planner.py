"""Remediation planning: maps a diagnosed root cause to a concrete, checked action.

Before recommending a reroute the planner *simulates* it on a copy of the
topology (target penalised / removed) so the risk statement reflects whether
every affected flow really has an alternative path.
"""

from __future__ import annotations

from dataclasses import replace

from app.models.detection import ComponentKind
from app.models.diagnosis import ActionType, RemediationPlan, RiskLevel, RootCause
from app.models.network import AdminStatus
from app.simulation.network import NetworkSimulator
from app.simulation.routing import build_routing_graph, shortest_path

NODE_AVOID_PENALTY_MS = 500.0
LINK_AVOID_PENALTY_MS = 500.0
RESTART_TICKS = 3
TARGET_UTILISATION = 0.70  # rate limiting aims to bring the source back under this


def simulate_avoidance(
    network: NetworkSimulator, target_id: str, kind: ComponentKind, flow_ids: list[str]
) -> dict[str, list[str] | None]:
    """Paths each flow would take if the target were avoided (None = unreachable)."""
    nodes = {k: replace(v) for k, v in network.nodes.items()}
    links = {k: replace(v) for k, v in network.links.items()}
    if kind == ComponentKind.NODE:
        nodes[target_id].penalty_ms += NODE_AVOID_PENALTY_MS
    else:
        links[target_id].penalty_ms += LINK_AVOID_PENALTY_MS
    graph = build_routing_graph(nodes, links)
    result: dict[str, list[str] | None] = {}
    for flow_id in flow_ids:
        flow = network.flows[flow_id]
        found = shortest_path(graph, flow.source, flow.destination)
        result[flow_id] = found[0] if found else None
    return result


def _avoids(path: list[str] | None, target_id: str, kind: ComponentKind, network: NetworkSimulator) -> bool:
    if not path:
        return False
    if kind == ComponentKind.NODE:
        return target_id not in path
    for u, v in zip(path, path[1:]):
        link = network.link_between(u, v)
        if link and link.id == target_id:
            return False
    return True


def build_plan(
    root_cause: RootCause,
    target_id: str,
    kind: ComponentKind,
    network: NetworkSimulator,
    affected_flows: list[str],
) -> RemediationPlan:
    flows_through = affected_flows or [f.id for f in (
        network.flows_through_node(target_id) if kind == ComponentKind.NODE else network.flows_through_link(target_id)
    )]
    alternatives = simulate_avoidance(network, target_id, kind, flows_through)
    rerouteable = [f for f, p in alternatives.items() if _avoids(p, target_id, kind, network)]
    stranded = [f for f in flows_through if f not in rerouteable]
    reroute_risk = RiskLevel.LOW if not stranded else RiskLevel.HIGH
    reroute_note = (
        f"All {len(rerouteable)} affected flow(s) have an alternative path."
        if not stranded
        else f"{len(stranded)} flow(s) have no alternative path and will stay degraded: {', '.join(stranded)}."
    )
    flow_list = ", ".join(flows_through) if flows_through else "none"

    needs_reroute = root_cause in (
        RootCause.ROUTER_CONGESTION,
        RootCause.NODE_FAILURE,
        RootCause.LINK_FAILURE,
        RootCause.PACKET_LOSS_SPIKE,
        RootCause.BANDWIDTH_SATURATION,
    )
    if needs_reroute and flows_through and not rerouteable:
        return RemediationPlan(
            action=ActionType.ESCALATE,
            target_id=target_id,
            target_kind=kind,
            summary=f"No alternative path around {target_id} - escalate to operator",
            rationale=f"{target_id} is the only path for flows {flow_list}; the topology offers nothing to reroute onto, so an automatic change cannot restore service. Capacity or redundancy is needed.",
            risk=RiskLevel.HIGH,
            expected_outcome="No automatic recovery; the incident stays open for manual intervention.",
            parameters={},
        )

    if root_cause == RootCause.ROUTER_CONGESTION:
        return RemediationPlan(
            action=ActionType.REROUTE_AROUND_NODE,
            target_id=target_id,
            target_kind=kind,
            summary=f"Temporarily reroute transit traffic away from {target_id}",
            rationale=f"{target_id} is saturated while its neighbours have spare capacity. Raising its routing cost moves flows {flow_list} onto healthy paths without touching the rest of the network. {reroute_note}",
            risk=reroute_risk,
            expected_outcome="End-to-end latency and packet loss on the rerouted flows return to baseline within a few samples; utilisation on the congested router falls as transit traffic leaves.",
            parameters={"penalty_ms": NODE_AVOID_PENALTY_MS},
        )
    if root_cause == RootCause.NODE_FAILURE:
        return RemediationPlan(
            action=ActionType.REROUTE_AROUND_NODE,
            target_id=target_id,
            target_kind=kind,
            summary=f"Recompute routes around unreachable node {target_id}",
            rationale=f"{target_id} is offline, so every flow still forwarded through it is black-holed. Recomputing the forwarding table excludes it. {reroute_note}",
            risk=reroute_risk,
            expected_outcome="Flows that were down come back on alternative paths; the node stays flagged until it returns.",
            parameters={"penalty_ms": NODE_AVOID_PENALTY_MS},
        )
    if root_cause == RootCause.NODE_OVERLOAD:
        return RemediationPlan(
            action=ActionType.RESTART_NODE,
            target_id=target_id,
            target_kind=kind,
            summary=f"Restart the forwarding service on {target_id} (traffic rerouted meanwhile)",
            rationale=f"CPU and memory are pegged while links are healthy, which points at a software condition on the node rather than the network. A controlled restart clears it; transit flows {flow_list} are rerouted for the restart window. {reroute_note}",
            risk=RiskLevel.MEDIUM,
            expected_outcome=f"{target_id} is unreachable for about {RESTART_TICKS} samples, then returns with CPU and memory back at baseline; primary routes are restored afterwards.",
            parameters={"restart_ticks": RESTART_TICKS, "penalty_ms": NODE_AVOID_PENALTY_MS},
        )
    if root_cause == RootCause.TRAFFIC_SPIKE:
        node = network.nodes[target_id]
        own_flows = [f for f in network.flows.values() if f.source == target_id]
        limit = max(50.0, TARGET_UTILISATION * node.capacity_mbps)
        per_flow = round(limit / max(1, len(own_flows)), 0)
        return RemediationPlan(
            action=ActionType.RATE_LIMIT_SOURCE,
            target_id=target_id,
            target_kind=kind,
            summary=f"Rate-limit traffic from {target_id} to {per_flow:.0f} Mbps per flow and rebalance uplinks",
            rationale=f"The surge originates at {target_id} itself (connections far above normal), so rerouting alone would just move the overload. Shaping its flows to a fair share keeps the switch under {TARGET_UTILISATION:.0%} utilisation while congestion-aware routing spreads the remaining load.",
            risk=RiskLevel.MEDIUM,
            expected_outcome="Utilisation on the switch and its uplink drop below the queueing threshold; delivered throughput stays at or above normal demand while the excess burst is shed.",
            parameters={"rate_limit_mbps": per_flow},
        )
    if root_cause == RootCause.LINK_FAILURE:
        return RemediationPlan(
            action=ActionType.ISOLATE_LINK,
            target_id=target_id,
            target_kind=kind,
            summary=f"Isolate failed link {target_id} and recompute routes",
            rationale=f"The link is down, so flows {flow_list} are black-holed until the forwarding table stops using it. Isolating it and recomputing routes restores them over the remaining topology. {reroute_note}",
            risk=reroute_risk,
            expected_outcome="Affected flows come back on alternative paths; the link stays isolated until it is repaired.",
            parameters={},
        )
    if root_cause in (RootCause.PACKET_LOSS_SPIKE, RootCause.BANDWIDTH_SATURATION):
        why = (
            "The link is dropping packets while its endpoints are healthy"
            if root_cause == RootCause.PACKET_LOSS_SPIKE
            else "The link has less capacity than the traffic offered to it"
        )
        return RemediationPlan(
            action=ActionType.REROUTE_AROUND_LINK,
            target_id=target_id,
            target_kind=kind,
            summary=f"Steer traffic off {target_id} onto its backup path",
            rationale=f"{why}, so moving flows {flow_list} to an alternative link removes the impairment without taking anything down. {reroute_note}",
            risk=reroute_risk,
            expected_outcome="Loss and latency on the rerouted flows return to baseline; the degraded link carries only background traffic until it recovers.",
            parameters={"penalty_ms": LINK_AVOID_PENALTY_MS},
        )
    return RemediationPlan(
        action=ActionType.MONITOR,
        target_id=target_id,
        target_kind=kind,
        summary=f"Keep monitoring {target_id}",
        rationale="The symptoms do not match a known signature strongly enough to act automatically.",
        risk=RiskLevel.LOW,
        expected_outcome="No change; the incident escalates if the anomaly persists.",
        parameters={},
    )


def node_is_up(network: NetworkSimulator, node_id: str) -> bool:
    return network.nodes[node_id].status == AdminStatus.UP
