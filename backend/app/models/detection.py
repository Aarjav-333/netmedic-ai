"""Pydantic schemas for anomaly detection output."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ComponentKind(str, Enum):
    NODE = "node"
    LINK = "link"
    FLOW = "flow"


class MetricDeviation(BaseModel):
    metric: str
    unit: str
    baseline: float = Field(description="Rolling healthy baseline for this component")
    current: float
    ratio: float = Field(description="current / baseline (inf-safe)")
    direction: str = Field(description="'up' or 'down'")

    def describe(self) -> str:
        unit = f" {self.unit}" if self.unit else ""
        label = self.metric.replace("_", " ")
        if self.metric.endswith("percent"):
            label = label.replace(" percent", "")
            unit = "%"
        return f"{label} {self.baseline:.1f}{unit} -> {self.current:.1f}{unit} ({self.ratio:.1f}x)"


class ComponentAnomaly(BaseModel):
    component_id: str
    component_kind: ComponentKind
    method: str = Field(description="'isolation_forest' for nodes, 'rules' for links/flows")
    decision_score: float | None = Field(
        default=None, description="Isolation Forest decision_function value (lower = more anomalous)"
    )
    severity: float = Field(
        ge=0,
        le=100,
        description="0-100 anomaly severity derived linearly from the decision score. Not a probability.",
    )
    is_anomaly: bool
    confirmed: bool = Field(description="Anomalous for at least CONFIRM_TICKS consecutive ticks")
    consecutive_ticks: int
    deviations: list[MetricDeviation] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list, description="Rule hits for links/flows")


class DetectionResult(BaseModel):
    tick: int
    timestamp: datetime
    anomalies: list[ComponentAnomaly] = Field(description="Only components currently flagged")
    node_scores: dict[str, float] = Field(description="Severity per node (0 = normal)")
    confirmed_ids: list[str]

    def anomaly(self, component_id: str) -> ComponentAnomaly | None:
        return next((a for a in self.anomalies if a.component_id == component_id), None)


class ModelInfoResponse(BaseModel):
    algorithm: str
    trained_at: str
    n_samples: int
    feature_names: list[str]
    contamination: float
    n_estimators: int
    threshold: float
    severity_span: float
    confirm_ticks: int
