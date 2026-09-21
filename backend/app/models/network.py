"""Pydantic schemas describing the simulated network (nodes, links, flows, routes)."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class NodeType(str, Enum):
    GATEWAY = "gateway"
    ROUTER = "router"
    SWITCH = "switch"
    SERVER = "server"


class HealthStatus(str, Enum):
    """Derived from telemetry each tick."""

    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    OFFLINE = "offline"


class AdminStatus(str, Enum):
    """Operational status of a node or link (independent of telemetry health)."""

    UP = "up"
    DOWN = "down"


class Position(BaseModel):
    x: float
    y: float


class NodeSchema(BaseModel):
    id: str
    name: str
    type: NodeType
    capacity_mbps: float = Field(description="Forwarding capacity of the node")
    status: AdminStatus = AdminStatus.UP
    health: HealthStatus = HealthStatus.HEALTHY
    position: Position
    penalty: float = Field(default=0.0, description="Routing penalty applied by the healing engine (ms)")
    isolated: bool = Field(default=False, description="True while the healing engine keeps transit traffic away")


class LinkSchema(BaseModel):
    id: str
    source: str
    target: str
    base_latency_ms: float
    capacity_mbps: float
    status: AdminStatus = AdminStatus.UP
    health: HealthStatus = HealthStatus.HEALTHY
    penalty: float = Field(default=0.0, description="Routing penalty applied by the healing engine (ms)")
    isolated: bool = False


class FlowSchema(BaseModel):
    id: str
    name: str
    source: str
    destination: str
    demand_mbps: float
    rate_limit_mbps: float | None = Field(default=None, description="Cap applied by the healing engine")


class RouteSchema(BaseModel):
    flow_id: str
    path: list[str] = Field(description="Ordered node ids from source to destination")
    links: list[str] = Field(description="Ordered link ids traversed")
    cost: float = Field(description="Total Dijkstra weight of the path")
    is_primary: bool = Field(description="True if this is the unpenalised shortest path")
    reason: str = Field(default="primary", description="Why this route was chosen")


class TopologyResponse(BaseModel):
    nodes: list[NodeSchema]
    links: list[LinkSchema]
    flows: list[FlowSchema]
    routes: list[RouteSchema]
