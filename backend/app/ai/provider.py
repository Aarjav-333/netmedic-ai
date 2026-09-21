"""AI explanation providers.

The GenAI layer never decides network truth. It receives the structured output
of the deterministic pipeline (detection + RCA + plan) and turns it into an
operator-friendly narrative. Two implementations:

- MockProvider     deterministic templates; always available (default)
- QualcommProvider Qualcomm Cloud AI Playground, configured *only* through
                   environment variables. Nothing about the endpoint, model or
                   credentials is hardcoded. See qualcomm.py.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from app.logging_config import get_logger
from app.models.ai import AIExplanation

log = get_logger("netmedic.ai")


class AIExplanationProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def explain(self, context: dict[str, Any]) -> AIExplanation:
        """Produce an explanation from the structured incident context."""


def build_context(incident) -> dict[str, Any]:
    """The structured payload handed to every provider (and shown in the UI on request)."""
    d = incident.diagnosis
    plan = incident.plan
    return {
        "incident_id": incident.id,
        "component": incident.component_id,
        "component_kind": incident.component_kind.value,
        "anomaly_severity": incident.anomaly_severity,
        "root_cause": incident.root_cause.value if incident.root_cause else None,
        "root_cause_label": incident.root_cause_label,
        "confidence": incident.confidence,
        "confidence_explanation": d.confidence_explanation if d else None,
        "evidence": list(d.evidence) if d else [],
        "affected_flows": list(d.affected_flows) if d else [],
        "recommended_action": plan.action.value if plan else None,
        "action_summary": plan.summary if plan else None,
        "action_rationale": plan.rationale if plan else None,
        "risk": plan.risk.value if plan else None,
        "expected_outcome": plan.expected_outcome if plan else None,
        "auto_heal": incident.auto_heal,
    }


class MockProvider(AIExplanationProvider):
    """Deterministic narrative built from the structured diagnosis - no network calls."""

    name = "mock"

    async def explain(self, context: dict[str, Any]) -> AIExplanation:
        started = time.perf_counter()
        component = context.get("component", "the component")
        label = (context.get("root_cause_label") or "an anomaly").lower()
        confidence = context.get("confidence") or 0.0
        evidence = list(context.get("evidence") or [])
        flows = context.get("affected_flows") or []
        action = context.get("action_summary") or "monitor the component"
        risk = (context.get("risk") or "low").lower()
        severity = context.get("anomaly_severity") or 0

        qualifier = "severe" if severity >= 80 else "significant" if severity >= 40 else "mild"
        diagnosis = f"{component} is experiencing {qualifier} {label}."
        impact = (
            f" Traffic on {', '.join(flows)} is affected." if flows else " No end-to-end flows are impacted yet."
        )
        explanation = (
            f"The anomaly detector flagged {component} with severity {severity:.0f}/100 and the root-cause engine matched the "
            f"'{label}' signature with {confidence:.0%} confidence. {context.get('confidence_explanation') or ''}".strip()
            + impact
        )
        justification = (
            f"Recommended action: {action}. {context.get('action_rationale') or ''} "
            f"This is the least invasive change that addresses the cause rather than the symptoms."
        ).replace("  ", " ").strip()
        risk_text = {
            "low": "Low - the change only affects routing preferences and is fully reversible.",
            "medium": "Medium - the action briefly changes how traffic is carried; service may blip while it takes effect.",
            "high": "High - no automatic path exists; manual intervention is required and service stays degraded meanwhile.",
        }.get(risk, risk)
        expectation = context.get("expected_outcome") or "Telemetry should return to baseline within a few samples."
        return AIExplanation(
            provider=self.name,
            model=None,
            diagnosis=diagnosis,
            explanation=explanation,
            evidence_summary=evidence[:6],
            remediation_justification=justification,
            operational_risk=risk_text,
            recovery_expectation=expectation,
            generated_at=datetime.now(timezone.utc),
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
        )


async def explain_with_fallback(provider: AIExplanationProvider, context: dict[str, Any]) -> AIExplanation:
    """Call the provider; on any failure produce the mock explanation flagged as a fallback."""
    try:
        return await provider.explain(context)
    except Exception as exc:  # noqa: BLE001 - the pipeline must never depend on the LLM
        log.warning("[AI] %s provider failed (%s); using mock explanation", provider.name, exc)
        result = await MockProvider().explain(context)
        result.fallback = True
        result.error = f"{provider.name}: {exc}"[:300]
        return result
