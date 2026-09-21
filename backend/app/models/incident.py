"""Pydantic schemas for incidents, healing actions and recovery verification."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from app.models.ai import AIExplanation
from app.models.detection import ComponentKind
from app.models.diagnosis import ActionType, Diagnosis, RemediationPlan, RootCause


class IncidentStatus(str, Enum):
    DETECTED = "detected"
    ANALYZING = "analyzing"
    DIAGNOSED = "diagnosed"
    REMEDIATING = "remediating"
    VERIFYING = "verifying"
    RESOLVED = "resolved"
    PARTIALLY_RESOLVED = "partially_resolved"
    FAILED = "failed"
    CANCELLED = "cancelled"


OPEN_STATUSES = {
    IncidentStatus.DETECTED,
    IncidentStatus.ANALYZING,
    IncidentStatus.DIAGNOSED,
    IncidentStatus.REMEDIATING,
    IncidentStatus.VERIFYING,
}

STATUS_LABEL: dict[IncidentStatus, str] = {
    IncidentStatus.DETECTED: "FAULT DETECTED",
    IncidentStatus.ANALYZING: "ANALYSING TELEMETRY",
    IncidentStatus.DIAGNOSED: "ROOT CAUSE IDENTIFIED",
    IncidentStatus.REMEDIATING: "AUTO-HEALING IN PROGRESS",
    IncidentStatus.VERIFYING: "VERIFYING RECOVERY",
    IncidentStatus.RESOLVED: "NETWORK RECOVERED",
    IncidentStatus.PARTIALLY_RESOLVED: "PARTIALLY RECOVERED",
    IncidentStatus.FAILED: "RECOVERY FAILED",
    IncidentStatus.CANCELLED: "CANCELLED",
}


class IncidentEvent(BaseModel):
    timestamp: datetime
    tick: int
    stage: IncidentStatus
    message: str


class RouteChange(BaseModel):
    flow_id: str
    before: list[str]
    after: list[str]


class HealingActionRecord(BaseModel):
    id: str
    incident_id: str
    action: ActionType
    target_id: str
    target_kind: ComponentKind
    parameters: dict[str, float | str] = Field(default_factory=dict)
    started_at: datetime
    completed_at: datetime | None = None
    result: str = Field(description="applied | skipped | failed | restored")
    details: str = ""
    route_changes: list[RouteChange] = Field(default_factory=list)


class MetricWindow(BaseModel):
    """Averages over a window of telemetry samples."""

    samples: int
    health_score: float
    avg_latency_ms: float = Field(description="Mean end-to-end latency of the affected flows")
    avg_packet_loss_percent: float
    affected_flows_healthy: int
    affected_flows_total: int
    target_latency_ms: float | None = None
    target_packet_loss_percent: float | None = None
    target_cpu_percent: float | None = None
    target_utilization_percent: float | None = None


class RecoveryCheck(BaseModel):
    name: str
    passed: bool
    detail: str


class RecoveryReport(BaseModel):
    status: IncidentStatus = Field(description="resolved | partially_resolved | failed")
    baseline: MetricWindow | None = Field(description="Before the anomaly appeared")
    before: MetricWindow = Field(description="Just before remediation")
    after: MetricWindow = Field(description="After the settle period")
    checks: list[RecoveryCheck]
    verified_at: datetime
    summary: str


class IncidentMetrics(BaseModel):
    time_to_detect_s: float | None = None
    time_to_diagnose_s: float | None = None
    time_to_remediate_s: float | None = None
    recovery_time_s: float | None = None
    total_duration_s: float | None = None


class Incident(BaseModel):
    id: str
    status: IncidentStatus
    status_label: str
    component_id: str
    component_kind: ComponentKind
    anomaly_severity: float
    first_abnormal_at: datetime
    detected_at: datetime
    diagnosed_at: datetime | None = None
    remediated_at: datetime | None = None
    verified_at: datetime | None = None
    resolved_at: datetime | None = None
    root_cause: RootCause | None = None
    root_cause_label: str | None = None
    confidence: float | None = None
    diagnosis: Diagnosis | None = None
    plan: RemediationPlan | None = None
    actions: list[HealingActionRecord] = Field(default_factory=list)
    recovery: RecoveryReport | None = None
    timeline: list[IncidentEvent] = Field(default_factory=list)
    metrics: IncidentMetrics = Field(default_factory=IncidentMetrics)
    ai_explanation: AIExplanation | None = Field(default=None, description="Filled by the AI explanation provider")
    auto_heal: bool = True

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_STATUSES


class IncidentSummary(BaseModel):
    id: str
    status: IncidentStatus
    status_label: str
    component_id: str
    root_cause_label: str | None
    confidence: float | None
    detected_at: datetime
    resolved_at: datetime | None
    action: ActionType | None
    recovery_time_s: float | None
    total_duration_s: float | None


class HealingModeRequest(BaseModel):
    auto_heal: bool


class HealingModeResponse(BaseModel):
    auto_heal: bool
