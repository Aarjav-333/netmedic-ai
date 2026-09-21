"""Pydantic schemas for telemetry samples and snapshots."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from app.models.network import AdminStatus, HealthStatus


class FlowStatus(str, Enum):
    OK = "ok"
    DEGRADED = "degraded"
    DOWN = "down"


class NodeTelemetry(BaseModel):
    node_id: str
    timestamp: datetime
    status: AdminStatus
    health: HealthStatus
    latency_ms: float = Field(description="Monitoring round-trip time to the node")
    packet_loss_percent: float
    throughput_mbps: float
    bandwidth_utilization_percent: float
    cpu_percent: float
    memory_percent: float
    active_connections: int
    health_score: float = Field(ge=0, le=100)


class LinkTelemetry(BaseModel):
    link_id: str
    source: str
    target: str
    timestamp: datetime
    status: AdminStatus
    health: HealthStatus
    latency_ms: float
    packet_loss_percent: float
    throughput_mbps: float
    utilization_percent: float
    capacity_mbps: float = Field(description="Effective capacity after any degradation")
    health_score: float = Field(ge=0, le=100)


class FlowTelemetry(BaseModel):
    flow_id: str
    name: str
    source: str
    destination: str
    path: list[str]
    links: list[str]
    status: FlowStatus
    health: HealthStatus
    latency_ms: float = Field(description="End-to-end latency along the current route")
    packet_loss_percent: float
    throughput_mbps: float
    demand_mbps: float
    is_primary_route: bool
    health_score: float = Field(ge=0, le=100)


class NetworkSummary(BaseModel):
    health_score: float = Field(ge=0, le=100, description="See app/telemetry/health.py for the formula")
    flow_health: float = Field(ge=0, le=100)
    node_health: float = Field(ge=0, le=100)
    link_health: float = Field(ge=0, le=100)
    active_nodes: int
    total_nodes: int
    active_links: int
    total_links: int
    avg_latency_ms: float = Field(description="Mean end-to-end latency over flows that are up")
    avg_node_latency_ms: float
    avg_packet_loss_percent: float = Field(description="Mean end-to-end packet loss over all flows")
    total_throughput_mbps: float
    total_demand_mbps: float
    rerouted_flows: int
    broken_flows: int


class TelemetrySnapshot(BaseModel):
    tick: int
    timestamp: datetime
    nodes: list[NodeTelemetry]
    links: list[LinkTelemetry]
    flows: list[FlowTelemetry]
    summary: NetworkSummary

    def node(self, node_id: str) -> NodeTelemetry | None:
        return next((n for n in self.nodes if n.node_id == node_id), None)

    def link(self, link_id: str) -> LinkTelemetry | None:
        return next((l for l in self.links if l.link_id == link_id), None)

    def flow(self, flow_id: str) -> FlowTelemetry | None:
        return next((f for f in self.flows if f.flow_id == flow_id), None)


class MetricPoint(BaseModel):
    """One compact time-series sample for charts."""

    tick: int
    timestamp: datetime
    health_score: float
    avg_latency_ms: float
    avg_packet_loss_percent: float
    total_throughput_mbps: float
    node_latency_ms: dict[str, float]
    node_cpu_percent: dict[str, float]
    node_utilization_percent: dict[str, float]
    node_packet_loss_percent: dict[str, float]


class TelemetryHistoryResponse(BaseModel):
    points: list[MetricPoint]
