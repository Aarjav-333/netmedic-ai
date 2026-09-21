"""Mutable runtime state for nodes, links, flows and routes."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.models.network import (
    AdminStatus,
    FlowSchema,
    HealthStatus,
    LinkSchema,
    NodeSchema,
    NodeType,
    Position,
    RouteSchema,
)


@dataclass
class NodeState:
    id: str
    name: str
    type: NodeType
    capacity_mbps: float
    base_rtt_ms: float
    x: float
    y: float
    status: AdminStatus = AdminStatus.UP
    health: HealthStatus = HealthStatus.HEALTHY
    penalty_ms: float = 0.0
    isolated: bool = False

    @property
    def is_up(self) -> bool:
        return self.status == AdminStatus.UP

    def to_schema(self) -> NodeSchema:
        return NodeSchema(
            id=self.id,
            name=self.name,
            type=self.type,
            capacity_mbps=self.capacity_mbps,
            status=self.status,
            health=self.health,
            position=Position(x=self.x, y=self.y),
            penalty=self.penalty_ms,
            isolated=self.isolated,
        )


@dataclass
class LinkState:
    id: str
    source: str
    target: str
    base_latency_ms: float
    capacity_mbps: float
    status: AdminStatus = AdminStatus.UP
    health: HealthStatus = HealthStatus.HEALTHY
    penalty_ms: float = 0.0
    isolated: bool = False

    @property
    def is_up(self) -> bool:
        return self.status == AdminStatus.UP

    def endpoints(self) -> tuple[str, str]:
        return self.source, self.target

    def other_end(self, node_id: str) -> str:
        return self.target if node_id == self.source else self.source

    def to_schema(self) -> LinkSchema:
        return LinkSchema(
            id=self.id,
            source=self.source,
            target=self.target,
            base_latency_ms=self.base_latency_ms,
            capacity_mbps=self.capacity_mbps,
            status=self.status,
            health=self.health,
            penalty=self.penalty_ms,
            isolated=self.isolated,
        )


@dataclass
class FlowState:
    id: str
    name: str
    source: str
    destination: str
    demand_mbps: float
    rate_limit_mbps: float | None = None

    @property
    def effective_demand_mbps(self) -> float:
        if self.rate_limit_mbps is None:
            return self.demand_mbps
        return min(self.demand_mbps, self.rate_limit_mbps)

    def to_schema(self) -> FlowSchema:
        return FlowSchema(
            id=self.id,
            name=self.name,
            source=self.source,
            destination=self.destination,
            demand_mbps=self.demand_mbps,
            rate_limit_mbps=self.rate_limit_mbps,
        )


@dataclass
class Route:
    flow_id: str
    path: list[str]
    links: list[str]
    cost: float
    is_primary: bool = True
    reason: str = "primary"
    primary_path: list[str] = field(default_factory=list)

    @property
    def is_broken(self) -> bool:
        """A flow with no usable path (e.g. every candidate link is down)."""
        return not self.path

    def to_schema(self) -> RouteSchema:
        return RouteSchema(
            flow_id=self.flow_id,
            path=list(self.path),
            links=list(self.links),
            cost=self.cost,
            is_primary=self.is_primary,
            reason=self.reason,
        )
