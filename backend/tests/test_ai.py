"""AI explanation providers."""

import json

import httpx
import pytest

from app.ai.provider import MockProvider, build_context, explain_with_fallback
from app.ai.qualcomm import QualcommProvider
from app.config import QualcommSettings
from app.engine import SimulationEngine
from app.models.faults import FaultType


@pytest.fixture(scope="module")
def local_engine() -> SimulationEngine:
    return SimulationEngine()


def diagnosed_incident(engine: SimulationEngine):
    engine.reset()
    for _ in range(8):
        engine.tick()
    engine.faults.inject(FaultType.ROUTER_CONGESTION, "R4")
    for _ in range(4):
        engine.tick()
    incident = engine.incidents.active
    assert incident is not None and incident.diagnosis is not None
    return incident


async def test_mock_provider_builds_narrative_from_structured_diagnosis(local_engine):
    incident = diagnosed_incident(local_engine)
    context = build_context(incident)
    assert context["root_cause"] == "router_congestion" and context["component"] == "R4"
    explanation = await MockProvider().explain(context)
    assert explanation.provider == "mock" and not explanation.fallback
    assert "R4" in explanation.diagnosis and "congestion" in explanation.diagnosis.lower()
    assert explanation.evidence_summary == incident.diagnosis.evidence[:6]
    assert "reroute" in explanation.remediation_justification.lower()
    assert explanation.operational_risk.lower().startswith("low")


def test_incident_receives_explanation_when_diagnosed(local_engine):
    incident = diagnosed_incident(local_engine)
    assert incident.ai_explanation is not None
    assert incident.ai_explanation.provider == "mock"


async def test_unconfigured_qualcomm_falls_back_to_mock():
    provider = QualcommProvider(QualcommSettings(base_url="", api_key="", model=""))
    assert not provider.is_configured
    result = await explain_with_fallback(provider, {"component": "R4", "root_cause_label": "Router congestion"})
    assert result.fallback is True and result.provider == "mock"
    assert "not configured" in (result.error or "")


async def test_qualcomm_provider_parses_openai_style_response(monkeypatch):
    settings = QualcommSettings(base_url="https://example.invalid/v1/chat/completions", api_key="test-key", model="test-model")
    provider = QualcommProvider(settings)
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        captured["body"] = json.loads(request.content)
        content = json.dumps(
            {
                "diagnosis": "R4 is congested.",
                "explanation": "Utilisation and CPU are saturated.",
                "evidence_summary": ["cpu 96%", "loss 13%"],
                "remediation_justification": "Rerouting removes transit load.",
                "operational_risk": "Low risk.",
                "recovery_expectation": "Flows recover in seconds.",
            }
        )
        return httpx.Response(200, json={"choices": [{"message": {"content": "```json\n" + content + "\n```"}}]})

    real_client = httpx.AsyncClient

    def fake_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", fake_client)
    result = await provider.explain({"component": "R4", "root_cause": "router_congestion"})
    assert result.provider == "qualcomm" and result.model == "test-model"
    assert result.diagnosis == "R4 is congested."
    assert result.evidence_summary == ["cpu 96%", "loss 13%"]
    assert captured["url"] == settings.base_url
    assert captured["auth"] == "Bearer test-key"
    assert captured["body"]["model"] == "test-model"
    assert captured["body"]["messages"][1]["content"].startswith("{")


async def test_qualcomm_provider_rejects_incomplete_json(monkeypatch):
    settings = QualcommSettings(base_url="https://example.invalid/chat", api_key="k", model="m")
    provider = QualcommProvider(settings)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"diagnosis": "only this"}'}}]})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: real_client(*a, transport=httpx.MockTransport(handler), **k))
    with pytest.raises(ValueError, match="missing keys"):
        await provider.explain({"component": "R4"})
    result = await explain_with_fallback(provider, {"component": "R4"})
    assert result.fallback and result.provider == "mock"


def test_ai_endpoints(client, engine):
    status = client.get("/api/ai/provider").json()
    assert status["active_provider"] == "mock" and status["ready"] is True
    assert client.post("/api/ai/explain/nope").status_code == 404
    client.post("/api/faults/inject", json={"fault_type": "router_congestion", "target_id": "R4"})
    for _ in range(4):
        engine.tick()
    incident = client.get("/api/incidents/active").json()
    res = client.post(f"/api/ai/explain/{incident['id']}")
    assert res.status_code == 200
    assert "R4" in res.json()["diagnosis"]
    assert client.get(f"/api/incidents/{incident['id']}").json()["ai_explanation"]["provider"] == "mock"
