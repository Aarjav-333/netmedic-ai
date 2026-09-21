"""Pydantic schemas for AI-generated explanations."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class AIExplanation(BaseModel):
    provider: str = Field(description="mock | qualcomm")
    model: str | None = None
    diagnosis: str = Field(description="One or two sentence diagnosis")
    explanation: str = Field(description="Why the engine reached this conclusion")
    evidence_summary: list[str]
    remediation_justification: str
    operational_risk: str
    recovery_expectation: str
    generated_at: datetime
    latency_ms: float
    fallback: bool = Field(default=False, description="True if the configured provider failed and the mock was used")
    error: str | None = None


class AIProviderStatus(BaseModel):
    configured_provider: str
    active_provider: str
    model: str | None
    ready: bool
    note: str
