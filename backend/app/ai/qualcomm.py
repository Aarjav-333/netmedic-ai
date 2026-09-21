"""Qualcomm Cloud AI Playground provider.

IMPORTANT - nothing about Qualcomm's API is hardcoded here. The operator supplies:

    QUALCOMM_AI_BASE_URL   full URL of the chat/completions endpoint
    QUALCOMM_AI_API_KEY    bearer token
    QUALCOMM_AI_MODEL      model identifier as named by the platform
    QUALCOMM_AI_TIMEOUT_SECONDS (optional)

ASSUMPTION (documented, not verified): the endpoint accepts an OpenAI-style
chat-completions JSON body ({"model", "messages", "temperature"}) with a Bearer
Authorization header and returns {"choices": [{"message": {"content": ...}}]}.
If Qualcomm Cloud AI Playground exposes a different contract, adapt
`_build_request` / `_extract_text` below - everything else stays the same.
Until the variables are set the engine uses MockProvider.
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from app.ai.provider import AIExplanationProvider
from app.config import QualcommSettings
from app.logging_config import get_logger
from app.models.ai import AIExplanation

log = get_logger("netmedic.ai.qualcomm")

SYSTEM_PROMPT = (
    "You are the explanation assistant of NetMedic AI, an autonomous network self-healing platform. "
    "You receive a STRUCTURED diagnosis produced by a deterministic analysis engine (anomaly detector, "
    "root-cause rules, remediation planner). Your job is to explain it clearly to a network operator. "
    "Never invent metrics, components or causes that are not in the input. Keep every field concise. "
    "Respond with a single JSON object with exactly these keys: "
    '"diagnosis" (1-2 sentences), "explanation" (2-4 sentences on why the engine reached this conclusion), '
    '"evidence_summary" (array of short strings, one per evidence item), '
    '"remediation_justification" (2-3 sentences), "operational_risk" (1-2 sentences, name the level), '
    '"recovery_expectation" (1-2 sentences).'
)

REQUIRED_KEYS = (
    "diagnosis",
    "explanation",
    "evidence_summary",
    "remediation_justification",
    "operational_risk",
    "recovery_expectation",
)


class QualcommProvider(AIExplanationProvider):
    name = "qualcomm"

    def __init__(self, settings: QualcommSettings) -> None:
        self.settings = settings

    @property
    def is_configured(self) -> bool:
        return self.settings.is_configured

    # ---------------------------------------------------------------- api
    def _build_request(self, context: dict[str, Any]) -> tuple[dict[str, str], dict[str, Any]]:
        headers = {
            "Authorization": f"Bearer {self.settings.api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": self.settings.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(context, indent=2)},
            ],
            "temperature": 0.2,
        }
        return headers, body

    @staticmethod
    def _extract_text(payload: dict[str, Any]) -> str:
        choices = payload.get("choices")
        if isinstance(choices, list) and choices:
            message = choices[0].get("message") or {}
            content = message.get("content") or choices[0].get("text")
            if isinstance(content, str):
                return content
        # Some gateways return the text at the top level.
        for key in ("output", "content", "text", "response"):
            if isinstance(payload.get(key), str):
                return payload[key]
        raise ValueError("Unrecognised response shape from AI endpoint")

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise ValueError("No JSON object in model output")
        data = json.loads(match.group(0))
        missing = [k for k in REQUIRED_KEYS if k not in data]
        if missing:
            raise ValueError(f"Model output missing keys: {', '.join(missing)}")
        if not isinstance(data["evidence_summary"], list):
            data["evidence_summary"] = [str(data["evidence_summary"])]
        return data

    async def explain(self, context: dict[str, Any]) -> AIExplanation:
        if not self.is_configured:
            raise RuntimeError("Qualcomm provider is not configured (QUALCOMM_AI_BASE_URL / API_KEY / MODEL)")
        headers, body = self._build_request(context)
        started = time.perf_counter()
        async with httpx.AsyncClient(timeout=self.settings.timeout_seconds) as client:
            response = await client.post(self.settings.base_url, headers=headers, json=body)
            response.raise_for_status()
            payload = response.json()
        text = self._extract_text(payload)
        data = self._parse_json(text)
        latency = (time.perf_counter() - started) * 1000
        log.info("[AI] Qualcomm explanation generated in %.0f ms", latency)
        return AIExplanation(
            provider=self.name,
            model=self.settings.model,
            diagnosis=str(data["diagnosis"]),
            explanation=str(data["explanation"]),
            evidence_summary=[str(x) for x in data["evidence_summary"]][:8],
            remediation_justification=str(data["remediation_justification"]),
            operational_risk=str(data["operational_risk"]),
            recovery_expectation=str(data["recovery_expectation"]),
            generated_at=datetime.now(timezone.utc),
            latency_ms=round(latency, 1),
        )
