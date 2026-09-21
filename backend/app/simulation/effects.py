"""Physical effects that active faults (and some remediations) impose on the simulation.

The telemetry generator only sees *effects* - extra load, degraded capacity,
added loss - never the fault type or label. This keeps ground truth out of the
detection / diagnosis pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class NodeEffects:
    extra_load_mbps: float = 0.0  # synthetic traffic occupying the node's capacity
    cpu_add_percent: float = 0.0
    memory_add_percent: float = 0.0
    latency_add_ms: float = 0.0
    packet_loss_add_percent: float = 0.0
    connections_multiplier: float = 1.0

    def merge(self, other: "NodeEffects") -> "NodeEffects":
        return NodeEffects(
            extra_load_mbps=self.extra_load_mbps + other.extra_load_mbps,
            cpu_add_percent=self.cpu_add_percent + other.cpu_add_percent,
            memory_add_percent=self.memory_add_percent + other.memory_add_percent,
            latency_add_ms=self.latency_add_ms + other.latency_add_ms,
            packet_loss_add_percent=self.packet_loss_add_percent + other.packet_loss_add_percent,
            connections_multiplier=self.connections_multiplier * other.connections_multiplier,
        )


@dataclass
class LinkEffects:
    capacity_multiplier: float = 1.0  # < 1.0 models bandwidth degradation
    latency_add_ms: float = 0.0
    packet_loss_add_percent: float = 0.0

    def merge(self, other: "LinkEffects") -> "LinkEffects":
        return LinkEffects(
            capacity_multiplier=self.capacity_multiplier * other.capacity_multiplier,
            latency_add_ms=self.latency_add_ms + other.latency_add_ms,
            packet_loss_add_percent=self.packet_loss_add_percent + other.packet_loss_add_percent,
        )


@dataclass
class FlowEffects:
    demand_multiplier: float = 1.0  # > 1.0 models a traffic spike from the source

    def merge(self, other: "FlowEffects") -> "FlowEffects":
        return FlowEffects(demand_multiplier=self.demand_multiplier * other.demand_multiplier)


@dataclass
class SimulationEffects:
    nodes: dict[str, NodeEffects] = field(default_factory=dict)
    links: dict[str, LinkEffects] = field(default_factory=dict)
    flows: dict[str, FlowEffects] = field(default_factory=dict)

    def node(self, node_id: str) -> NodeEffects:
        return self.nodes.get(node_id, NodeEffects())

    def link(self, link_id: str) -> LinkEffects:
        return self.links.get(link_id, LinkEffects())

    def flow(self, flow_id: str) -> FlowEffects:
        return self.flows.get(flow_id, FlowEffects())

    def add_node(self, node_id: str, effects: NodeEffects) -> None:
        self.nodes[node_id] = self.node(node_id).merge(effects)

    def add_link(self, link_id: str, effects: LinkEffects) -> None:
        self.links[link_id] = self.link(link_id).merge(effects)

    def add_flow(self, flow_id: str, effects: FlowEffects) -> None:
        self.flows[flow_id] = self.flow(flow_id).merge(effects)

    @property
    def is_empty(self) -> bool:
        return not (self.nodes or self.links or self.flows)
