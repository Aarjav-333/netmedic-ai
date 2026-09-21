"""Hypothesis rules for root-cause analysis.

Every rule is a soft condition: strength = clamp((value - ok) / (bad - ok), 0, 1),
so a hypothesis score is the weighted mean of how strongly its conditions hold.
The weights are deliberately visible - they are the explanation.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.detection.features import expected_connections
from app.models.detection import ComponentKind
from app.models.diagnosis import Hypothesis, RootCause, RuleCheck
from app.models.network import AdminStatus
from app.models.telemetry import LinkTelemetry, NodeTelemetry, TelemetrySnapshot
from app.simulation.network import NetworkSimulator


def soft(value: float, ok: float, bad: float) -> float:
    """0 while value <= ok, 1 once value >= bad, linear between."""
    if bad == ok:
        return 1.0 if value >= bad else 0.0
    return max(0.0, min(1.0, (value - ok) / (bad - ok)))


@dataclass
class Context:
    network: NetworkSimulator
    snapshot: TelemetrySnapshot

    def node(self, node_id: str) -> NodeTelemetry:
        sample = self.snapshot.node(node_id)
        assert sample is not None
        return sample

    def link(self, link_id: str) -> LinkTelemetry:
        sample = self.snapshot.link(link_id)
        assert sample is not None
        return sample

    def latency_ratio(self, node: NodeTelemetry) -> float:
        return node.latency_ms / self.network.nodes[node.node_id].base_rtt_ms

    def connections_ratio(self, node: NodeTelemetry) -> float:
        return node.active_connections / expected_connections(self.network.nodes[node.node_id])

    def link_latency_ratio(self, link: LinkTelemetry) -> float:
        base = self.network.links[link.link_id].base_latency_ms
        return link.latency_ms / base if base else 1.0

    def neighbour_nodes(self, node_id: str) -> list[NodeTelemetry]:
        return [self.node(n) for n in self.network.neighbors(node_id)]

    def incident_links(self, node_id: str) -> list[LinkTelemetry]:
        return [self.link(l.id) for l in self.network.links_of(node_id)]

    def mean_health(self, samples: list[NodeTelemetry] | list[LinkTelemetry]) -> float:
        return sum(s.health_score for s in samples) / len(samples) / 100 if samples else 1.0


def _hypothesis(root_cause: RootCause, target_id: str, kind: ComponentKind, checks: list[RuleCheck]) -> Hypothesis:
    total_weight = sum(c.weight for c in checks) or 1.0
    score = sum(c.weight * c.strength for c in checks) / total_weight
    return Hypothesis(root_cause=root_cause, target_id=target_id, target_kind=kind, score=round(score, 3), checks=checks)


def check(condition: str, weight: float, strength: float, observation: str) -> RuleCheck:
    return RuleCheck(condition=condition, weight=weight, strength=round(strength, 3), observation=observation)


# ----------------------------------------------------------------- node rules
def router_congestion(ctx: Context, node_id: str) -> Hypothesis:
    n = ctx.node(node_id)
    neighbours = ctx.neighbour_nodes(node_id)
    healthy_neighbours = [x.node_id for x in neighbours if x.health_score >= 85]
    checks = [
        check("utilisation high", 3, soft(n.bandwidth_utilization_percent, 75, 100), f"utilisation {n.bandwidth_utilization_percent:.0f}%"),
        check("CPU high", 2, soft(n.cpu_percent, 65, 95), f"CPU {n.cpu_percent:.0f}%"),
        check("latency elevated", 2, soft(ctx.latency_ratio(n), 1.5, 5.0), f"latency {n.latency_ms:.0f} ms ({ctx.latency_ratio(n):.1f}x baseline)"),
        check("packet loss elevated", 2, soft(n.packet_loss_percent, 0.8, 8.0), f"packet loss {n.packet_loss_percent:.1f}%"),
        check("neighbours healthy", 1, ctx.mean_health(neighbours), f"{len(healthy_neighbours)}/{len(neighbours)} neighbours healthy"),
        check("not a demand spike at source", 1, 1 - soft(ctx.connections_ratio(n), 1.6, 3.5), f"connections {ctx.connections_ratio(n):.1f}x expected"),
    ]
    return _hypothesis(RootCause.ROUTER_CONGESTION, node_id, ComponentKind.NODE, checks)


def node_overload(ctx: Context, node_id: str) -> Hypothesis:
    n = ctx.node(node_id)
    links = ctx.incident_links(node_id)
    checks = [
        check("CPU very high", 3, soft(n.cpu_percent, 70, 95), f"CPU {n.cpu_percent:.0f}%"),
        check("memory high", 2, soft(n.memory_percent, 65, 90), f"memory {n.memory_percent:.0f}%"),
        check("utilisation normal", 2, 1 - soft(n.bandwidth_utilization_percent, 70, 95), f"utilisation {n.bandwidth_utilization_percent:.0f}%"),
        check("attached links healthy", 1, ctx.mean_health(links), f"{sum(1 for l in links if l.health_score >= 85)}/{len(links)} links healthy"),
        check("latency mildly elevated", 1, soft(ctx.latency_ratio(n), 1.2, 3.0), f"latency {n.latency_ms:.0f} ms"),
    ]
    return _hypothesis(RootCause.NODE_OVERLOAD, node_id, ComponentKind.NODE, checks)


def traffic_spike(ctx: Context, node_id: str) -> Hypothesis:
    n = ctx.node(node_id)
    links = ctx.incident_links(node_id)
    worst_link = max((l.utilization_percent for l in links), default=0.0)
    capacity = ctx.network.nodes[node_id].capacity_mbps
    checks = [
        check("connections far above expected", 3, soft(ctx.connections_ratio(n), 1.5, 3.5), f"connections {ctx.connections_ratio(n):.1f}x expected"),
        check("utilisation high", 2, soft(n.bandwidth_utilization_percent, 80, 120), f"utilisation {n.bandwidth_utilization_percent:.0f}%"),
        check("uplink saturated", 2, soft(worst_link, 80, 110), f"busiest uplink {worst_link:.0f}%"),
        check("packet loss elevated", 1, soft(n.packet_loss_percent, 0.8, 8.0), f"packet loss {n.packet_loss_percent:.1f}%"),
        check("throughput at capacity", 1, soft(n.throughput_mbps / capacity, 0.8, 1.0), f"throughput {n.throughput_mbps:.0f} of {capacity:.0f} Mbps"),
    ]
    return _hypothesis(RootCause.TRAFFIC_SPIKE, node_id, ComponentKind.NODE, checks)


def node_failure(ctx: Context, node_id: str) -> Hypothesis:
    n = ctx.node(node_id)
    down = n.status == AdminStatus.DOWN
    checks = [check("node unreachable", 1, 1.0 if down else 0.0, "no telemetry" if down else "telemetry present")]
    return _hypothesis(RootCause.NODE_FAILURE, node_id, ComponentKind.NODE, checks)


# ----------------------------------------------------------------- link rules
def link_failure(ctx: Context, link_id: str) -> Hypothesis:
    l = ctx.link(link_id)
    down = l.status == AdminStatus.DOWN
    checks = [check("link down", 1, 1.0 if down else 0.0, "status DOWN" if down else "status UP")]
    return _hypothesis(RootCause.LINK_FAILURE, link_id, ComponentKind.LINK, checks)


def packet_loss_spike(ctx: Context, link_id: str) -> Hypothesis:
    l = ctx.link(link_id)
    endpoints = [ctx.node(l.source), ctx.node(l.target)]
    checks = [
        check("packet loss high", 3, soft(l.packet_loss_percent, 1.0, 8.0), f"loss {l.packet_loss_percent:.1f}%"),
        check("utilisation normal", 2, 1 - soft(l.utilization_percent, 75, 95), f"utilisation {l.utilization_percent:.0f}%"),
        check("latency normal", 1, 1 - soft(ctx.link_latency_ratio(l), 2.0, 5.0), f"latency {ctx.link_latency_ratio(l):.1f}x baseline"),
        check("endpoints healthy", 1, ctx.mean_health(endpoints), f"{l.source}/{l.target} health {endpoints[0].health_score:.0f}/{endpoints[1].health_score:.0f}"),
    ]
    return _hypothesis(RootCause.PACKET_LOSS_SPIKE, link_id, ComponentKind.LINK, checks)


def bandwidth_saturation(ctx: Context, link_id: str) -> Hypothesis:
    l = ctx.link(link_id)
    nominal = ctx.network.links[link_id].capacity_mbps
    endpoints = [ctx.node(l.source), ctx.node(l.target)]
    spike_at_endpoint = max(soft(ctx.connections_ratio(n), 1.5, 3.5) for n in endpoints)
    capacity_drop = 1 - l.capacity_mbps / nominal if nominal else 0.0
    checks = [
        check("utilisation at or above capacity", 3, soft(l.utilization_percent, 85, 105), f"utilisation {l.utilization_percent:.0f}%"),
        check("negotiated capacity reduced", 2, soft(capacity_drop, 0.1, 0.5), f"capacity {l.capacity_mbps:.0f} of {nominal:.0f} Mbps"),
        check("throughput plateaued at capacity", 1, soft(l.throughput_mbps / l.capacity_mbps if l.capacity_mbps else 0, 0.85, 1.0), f"throughput {l.throughput_mbps:.0f} Mbps"),
        check("latency elevated", 1, soft(ctx.link_latency_ratio(l), 1.5, 5.0), f"latency {ctx.link_latency_ratio(l):.1f}x baseline"),
        check("packet loss elevated", 1, soft(l.packet_loss_percent, 0.8, 8.0), f"loss {l.packet_loss_percent:.1f}%"),
        check("no demand spike at endpoints", 2, 1 - spike_at_endpoint, f"endpoint connections {max(ctx.connections_ratio(n) for n in endpoints):.1f}x expected"),
    ]
    return _hypothesis(RootCause.BANDWIDTH_SATURATION, link_id, ComponentKind.LINK, checks)


NODE_HYPOTHESES = (router_congestion, node_overload, traffic_spike, node_failure)
LINK_HYPOTHESES = (link_failure, packet_loss_spike, bandwidth_saturation)
