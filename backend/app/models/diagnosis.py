"""Pydantic schemas for root-cause analysis and remediation planning."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from app.models.detection import ComponentKind


class RootCause(str, Enum):
    ROUTER_CONGESTION = "router_congestion"
    NODE_OVERLOAD = "node_overload"
    TRAFFIC_SPIKE = "traffic_spike"
    NODE_FAILURE = "node_failure"
    LINK_FAILURE = "link_failure"
    PACKET_LOSS_SPIKE = "packet_loss_spike"
    BANDWIDTH_SATURATION = "bandwidth_saturation"
    UNKNOWN = "unknown"


ROOT_CAUSE_LABEL: dict[RootCause, str] = {
    RootCause.ROUTER_CONGESTION: "Router congestion",
    RootCause.NODE_OVERLOAD: "Node overload (CPU / memory)",
    RootCause.TRAFFIC_SPIKE: "Traffic spike at source",
    RootCause.NODE_FAILURE: "Node failure",
    RootCause.LINK_FAILURE: "Link failure",
    RootCause.PACKET_LOSS_SPIKE: "Packet-loss spike on link",
    RootCause.BANDWIDTH_SATURATION: "Bandwidth saturation on link",
    RootCause.UNKNOWN: "Unclassified anomaly",
}


class ActionType(str, Enum):
    REROUTE_AROUND_NODE = "reroute_around_node"
    REROUTE_AROUND_LINK = "reroute_around_link"
    ISOLATE_LINK = "isolate_link"
    RESTART_NODE = "restart_node"
    RATE_LIMIT_SOURCE = "rate_limit_source"
    REDISTRIBUTE_LOAD = "redistribute_load"
    ESCALATE = "escalate"
    MONITOR = "monitor"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RuleCheck(BaseModel):
    """One scored condition inside a hypothesis."""

    condition: str
    weight: float
    strength: float = Field(ge=0, le=1, description="How strongly the condition holds (0-1)")
    observation: str


class Hypothesis(BaseModel):
    root_cause: RootCause
    target_id: str
    target_kind: ComponentKind
    score: float = Field(ge=0, le=1, description="Weighted rule-match score")
    checks: list[RuleCheck]


class RemediationPlan(BaseModel):
    action: ActionType
    target_id: str
    target_kind: ComponentKind
    summary: str
    rationale: str
    risk: RiskLevel
    expected_outcome: str
    parameters: dict[str, float | str] = Field(default_factory=dict)


class Diagnosis(BaseModel):
    tick: int
    timestamp: datetime
    root_cause: RootCause
    root_cause_label: str
    target_id: str
    target_kind: ComponentKind
    confidence: float = Field(ge=0, le=1)
    confidence_explanation: str
    evidence: list[str]
    affected_flows: list[str]
    affected_components: list[str] = Field(description="Every component currently flagged by detection")
    hypotheses: list[Hypothesis] = Field(description="All scored hypotheses, best first")
    anomaly_severity: float = Field(ge=0, le=100)
    plan: RemediationPlan
