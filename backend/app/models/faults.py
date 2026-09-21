"""Pydantic schemas for fault injection."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class FaultType(str, Enum):
    ROUTER_CONGESTION = "router_congestion"
    LINK_FAILURE = "link_failure"
    PACKET_LOSS_SPIKE = "packet_loss_spike"
    BANDWIDTH_DEGRADATION = "bandwidth_degradation"
    NODE_OVERLOAD = "node_overload"
    TRAFFIC_SPIKE = "traffic_spike"
    ROUTER_FAILURE = "router_failure"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TargetKind(str, Enum):
    NODE = "node"
    LINK = "link"


class FaultDefinition(BaseModel):
    """Catalog entry describing a fault type for the UI."""

    type: FaultType
    label: str
    description: str
    target_kind: TargetKind
    node_types: list[str] = Field(default_factory=list, description="Allowed node types when target_kind=node")


class InjectFaultRequest(BaseModel):
    fault_type: FaultType
    target_id: str = Field(description="Node id (e.g. R4) or link id (e.g. L-R4-SW3)")
    severity: Severity = Severity.MEDIUM
    duration_seconds: float | None = Field(
        default=None, ge=1, le=3600, description="Auto-clear after this many seconds (omit = until reset)"
    )


class ActiveFaultSchema(BaseModel):
    id: str
    type: FaultType
    label: str
    target_id: str
    target_kind: TargetKind
    severity: Severity
    injected_at: datetime
    expires_at: datetime | None
    cleared_at: datetime | None = None
    cleared_by: str | None = None

    @property
    def is_active(self) -> bool:
        return self.cleared_at is None


class FaultListResponse(BaseModel):
    active: list[ActiveFaultSchema]
    catalog: list[FaultDefinition]


class ResetResponse(BaseModel):
    cleared_faults: int
    message: str
