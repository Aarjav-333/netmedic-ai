"""Telemetry generator: turns routing state + fault effects into realistic samples.

Everything is derived from *physical* quantities of the simulation:

    node load    = traffic routed through the node (from the routing table)
                 + small background load
                 + synthetic load imposed by active fault effects
    utilisation  = load / capacity
    queue factor = 0 below 60 % utilisation, growing quadratically to a cap
    latency      = base RTT * (1 + queue factor) + fault latency + noise
    packet loss  = base loss + saturation loss (above 85 %) + fault loss
    cpu          = 12 + 55 * utilisation + fault cpu + noise

Flows are measured end-to-end along their *current* route, so a reroute
performed by the healing engine changes flow telemetry for real.

Noise is an AR(1) process per metric so values drift smoothly instead of
jumping around every sample.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

from app.models.network import AdminStatus, HealthStatus
from app.models.telemetry import (
    FlowStatus,
    FlowTelemetry,
    LinkTelemetry,
    NetworkSummary,
    NodeTelemetry,
    TelemetrySnapshot,
)
from app.simulation.effects import SimulationEffects
from app.simulation.network import NetworkSimulator
from app.simulation.state import FlowState, LinkState, NodeState
from app.telemetry.health import (
    FLOW_BANDS,
    LINK_BANDS,
    NODE_BANDS,
    component_score,
    network_health_score,
    status_from_score,
)

# --- tunables -------------------------------------------------------------
QUEUE_START_UTIL = 0.60
QUEUE_GAIN = 5.0
QUEUE_CAP = 8.0
LOSS_START_UTIL = 0.85
LOSS_GAIN_PERCENT = 60.0  # % loss per unit of utilisation above LOSS_START_UTIL
BACKGROUND_LOAD_FRACTION = 0.04
NODE_BASE_LOSS = 0.08
LINK_BASE_LOSS = 0.03
AR_PERSISTENCE = 0.75

BASE_CONNECTIONS = {"gateway": 2200, "router": 480, "switch": 140, "server": 320}
CORE_CONNECTIONS = 1600


def queue_factor(utilization: float) -> float:
    if utilization <= QUEUE_START_UTIL:
        return 0.0
    over = (utilization - QUEUE_START_UTIL) / (1.0 - QUEUE_START_UTIL)
    return min(QUEUE_CAP, over * over * QUEUE_GAIN)


def saturation_loss(utilization: float) -> float:
    return max(0.0, utilization - LOSS_START_UTIL) * LOSS_GAIN_PERCENT


class TelemetryGenerator:
    def __init__(self, network: NetworkSimulator, seed: int | None = None) -> None:
        self.network = network
        self._rng = np.random.default_rng(seed)
        self._noise: dict[str, float] = {}

    # ------------------------------------------------------------- noise
    def _noise_value(self, key: str) -> float:
        """Unit-variance AR(1) noise, persistent per key."""
        previous = self._noise.get(key, 0.0)
        value = AR_PERSISTENCE * previous + (1 - AR_PERSISTENCE) * self._rng.normal()
        self._noise[key] = value
        # AR(1) variance is (1-p)^2 / (1-p^2); rescale to unit std.
        scale = ((1 - AR_PERSISTENCE) ** 2 / (1 - AR_PERSISTENCE**2)) ** 0.5
        return value / scale

    def reset_noise(self) -> None:
        self._noise.clear()

    # -------------------------------------------------------------- loads
    def _flow_demand(self, flow: FlowState, effects: SimulationEffects) -> float:
        offered = flow.demand_mbps * effects.flow(flow.id).demand_multiplier
        if flow.rate_limit_mbps is not None:
            offered = min(offered, flow.rate_limit_mbps)
        return offered

    def _routed_loads(self, effects: SimulationEffects) -> tuple[dict[str, float], dict[str, float]]:
        node_loads = {node_id: 0.0 for node_id in self.network.nodes}
        link_loads = {link_id: 0.0 for link_id in self.network.links}
        for route in self.network.routes.values():
            if route.is_broken:
                continue
            demand = self._flow_demand(self.network.flows[route.flow_id], effects)
            for node_id in route.path:
                node_loads[node_id] += demand
            for link_id in route.links:
                link_loads[link_id] += demand
        return node_loads, link_loads

    # ----------------------------------------------------------- generate
    def generate(self, tick: int, effects: SimulationEffects | None = None) -> TelemetrySnapshot:
        effects = effects or SimulationEffects()
        now = datetime.now(timezone.utc)
        node_loads, link_loads = self._routed_loads(effects)

        nodes = [self._node_sample(n, node_loads[n.id], effects, now) for n in self.network.nodes.values()]
        links = [self._link_sample(l, link_loads[l.id], effects, now) for l in self.network.links.values()]
        node_by_id = {n.node_id: n for n in nodes}
        link_by_id = {l.link_id: l for l in links}
        flows = [self._flow_sample(f, node_by_id, link_by_id, effects, now) for f in self.network.flows.values()]

        # Push derived health back onto the simulator state so the topology API reflects it.
        for n in nodes:
            self.network.nodes[n.node_id].health = n.health
        for l in links:
            self.network.links[l.link_id].health = l.health

        summary = self._summary(nodes, links, flows)
        return TelemetrySnapshot(tick=tick, timestamp=now, nodes=nodes, links=links, flows=flows, summary=summary)

    # ---------------------------------------------------------- per-node
    def _node_sample(self, node: NodeState, routed_load: float, effects: SimulationEffects, now: datetime) -> NodeTelemetry:
        fx = effects.node(node.id)
        if not node.is_up:
            return NodeTelemetry(
                node_id=node.id, timestamp=now, status=AdminStatus.DOWN, health=HealthStatus.OFFLINE,
                latency_ms=0.0, packet_loss_percent=100.0, throughput_mbps=0.0,
                bandwidth_utilization_percent=0.0, cpu_percent=0.0, memory_percent=0.0,
                active_connections=0, health_score=0.0,
            )

        background = node.capacity_mbps * BACKGROUND_LOAD_FRACTION * (1 + 0.3 * self._noise_value(f"{node.id}:bg"))
        load = max(0.0, routed_load + background + fx.extra_load_mbps)
        util = load / node.capacity_mbps

        latency = node.base_rtt_ms * (1 + queue_factor(util)) + fx.latency_add_ms + 2.5 * self._noise_value(f"{node.id}:lat")
        loss = NODE_BASE_LOSS + saturation_loss(util) + fx.packet_loss_add_percent + 0.12 * abs(self._noise_value(f"{node.id}:loss"))
        cpu = 12 + 55 * min(util, 1.3) + fx.cpu_add_percent + 3.0 * self._noise_value(f"{node.id}:cpu")
        memory = 35 + 22 * min(util, 1.3) + fx.memory_add_percent + 2.0 * self._noise_value(f"{node.id}:mem")
        base_conn = CORE_CONNECTIONS if node.id == "R1" else BASE_CONNECTIONS[node.type.value]
        connections = base_conn * (0.7 + 0.6 * min(util, 1.3)) * fx.connections_multiplier * (1 + 0.08 * self._noise_value(f"{node.id}:conn"))
        loss = min(100.0, max(0.0, loss))
        throughput = min(load, node.capacity_mbps) * (1 - loss / 100)

        values = {
            "latency_ms": latency,
            "packet_loss_percent": loss,
            "cpu_percent": cpu,
            "memory_percent": memory,
            "bandwidth_utilization_percent": util * 100,
        }
        score = component_score(NODE_BANDS, values)
        return NodeTelemetry(
            node_id=node.id,
            timestamp=now,
            status=AdminStatus.UP,
            health=status_from_score(score),
            latency_ms=round(max(1.0, latency), 1),
            packet_loss_percent=round(loss, 2),
            throughput_mbps=round(throughput, 1),
            bandwidth_utilization_percent=round(min(util * 100, 150.0), 1),
            cpu_percent=round(min(100.0, max(1.0, cpu)), 1),
            memory_percent=round(min(100.0, max(5.0, memory)), 1),
            active_connections=int(max(0, connections)),
            health_score=score,
        )

    # ---------------------------------------------------------- per-link
    def _link_sample(self, link: LinkState, routed_load: float, effects: SimulationEffects, now: datetime) -> LinkTelemetry:
        fx = effects.link(link.id)
        capacity = link.capacity_mbps * max(0.01, fx.capacity_multiplier)
        if not link.is_up:
            return LinkTelemetry(
                link_id=link.id, source=link.source, target=link.target, timestamp=now,
                status=AdminStatus.DOWN, health=HealthStatus.OFFLINE, latency_ms=0.0,
                packet_loss_percent=100.0, throughput_mbps=0.0, utilization_percent=0.0,
                capacity_mbps=capacity, health_score=0.0,
            )
        background = link.capacity_mbps * 0.02 * (1 + 0.3 * self._noise_value(f"{link.id}:bg"))
        load = max(0.0, routed_load + background)
        util = load / capacity
        latency = link.base_latency_ms * (1 + queue_factor(util)) + fx.latency_add_ms + 0.4 * abs(self._noise_value(f"{link.id}:lat"))
        loss = LINK_BASE_LOSS + saturation_loss(util) + fx.packet_loss_add_percent + 0.05 * abs(self._noise_value(f"{link.id}:loss"))
        loss = min(100.0, max(0.0, loss))
        throughput = min(load, capacity) * (1 - loss / 100)
        values = {
            "packet_loss_percent": loss,
            "utilization_percent": util * 100,
            "latency_ratio": latency / link.base_latency_ms,
        }
        score = component_score(LINK_BANDS, values)
        return LinkTelemetry(
            link_id=link.id,
            source=link.source,
            target=link.target,
            timestamp=now,
            status=AdminStatus.UP,
            health=status_from_score(score),
            latency_ms=round(latency, 2),
            packet_loss_percent=round(loss, 2),
            throughput_mbps=round(throughput, 1),
            utilization_percent=round(min(util * 100, 150.0), 1),
            capacity_mbps=round(capacity, 1),
            health_score=score,
        )

    # ---------------------------------------------------------- per-flow
    def _flow_sample(
        self,
        flow: FlowState,
        nodes: dict[str, NodeTelemetry],
        links: dict[str, LinkTelemetry],
        effects: SimulationEffects,
        now: datetime,
    ) -> FlowTelemetry:
        route = self.network.routes[flow.id]
        offered = self._flow_demand(flow, effects)
        path_nodes = [nodes[n] for n in route.path]
        path_links = [links[l] for l in route.links]
        is_down = route.is_broken or any(n.status == AdminStatus.DOWN for n in path_nodes) or any(
            l.status == AdminStatus.DOWN for l in path_links
        )
        if is_down:
            return FlowTelemetry(
                flow_id=flow.id, name=flow.name, source=flow.source, destination=flow.destination,
                path=list(route.path), links=list(route.links), status=FlowStatus.DOWN,
                health=HealthStatus.OFFLINE, latency_ms=0.0, packet_loss_percent=100.0,
                throughput_mbps=0.0, demand_mbps=flow.demand_mbps, is_primary_route=route.is_primary,
                health_score=0.0,
            )

        # Latency: link latencies + queueing delay experienced at each transit node.
        latency = sum(l.latency_ms for l in path_links)
        survival = 1.0
        delivery_ratio = 1.0
        for l in path_links:
            survival *= 1 - l.packet_loss_percent / 100
            if l.utilization_percent > 100:
                delivery_ratio = min(delivery_ratio, 100 / l.utilization_percent)
        for n in path_nodes[1:-1]:
            state = self.network.nodes[n.node_id]
            latency += max(0.0, n.latency_ms - state.base_rtt_ms)  # queueing delay beyond baseline RTT
            survival *= 1 - n.packet_loss_percent / 100
            if n.bandwidth_utilization_percent > 100:
                delivery_ratio = min(delivery_ratio, 100 / n.bandwidth_utilization_percent)
        loss = (1 - survival) * 100
        throughput = offered * delivery_ratio * survival
        shortfall = max(0.0, 100 * (1 - throughput / flow.demand_mbps))

        values = {
            "latency_ms": latency,
            "packet_loss_percent": loss,
            "delivery_shortfall_percent": shortfall,
        }
        score = component_score(FLOW_BANDS, values)
        health = status_from_score(score)
        status = FlowStatus.OK if health == HealthStatus.HEALTHY else FlowStatus.DEGRADED
        return FlowTelemetry(
            flow_id=flow.id,
            name=flow.name,
            source=flow.source,
            destination=flow.destination,
            path=list(route.path),
            links=list(route.links),
            status=status,
            health=health,
            latency_ms=round(latency, 1),
            packet_loss_percent=round(loss, 2),
            throughput_mbps=round(throughput, 1),
            demand_mbps=flow.demand_mbps,
            is_primary_route=route.is_primary,
            health_score=score,
        )

    # ------------------------------------------------------------ summary
    def _summary(self, nodes: list[NodeTelemetry], links: list[LinkTelemetry], flows: list[FlowTelemetry]) -> NetworkSummary:
        health, flow_health, node_health, link_health = network_health_score(
            [f.health_score for f in flows], [n.health_score for n in nodes], [l.health_score for l in links]
        )
        up_nodes = [n for n in nodes if n.status == AdminStatus.UP]
        live_flows = [f for f in flows if f.status != FlowStatus.DOWN]
        return NetworkSummary(
            health_score=health,
            flow_health=flow_health,
            node_health=node_health,
            link_health=link_health,
            active_nodes=len(up_nodes),
            total_nodes=len(nodes),
            active_links=sum(1 for l in links if l.status == AdminStatus.UP),
            total_links=len(links),
            avg_latency_ms=round(sum(f.latency_ms for f in live_flows) / len(live_flows), 1) if live_flows else 0.0,
            avg_node_latency_ms=round(sum(n.latency_ms for n in up_nodes) / len(up_nodes), 1) if up_nodes else 0.0,
            avg_packet_loss_percent=round(sum(f.packet_loss_percent for f in flows) / len(flows), 2) if flows else 0.0,
            total_throughput_mbps=round(sum(f.throughput_mbps for f in flows), 1),
            total_demand_mbps=round(sum(f.demand_mbps for f in flows), 1),
            rerouted_flows=sum(1 for f in flows if not f.is_primary_route and f.status != FlowStatus.DOWN),
            broken_flows=sum(1 for f in flows if f.status == FlowStatus.DOWN),
        )
