"""Provider selection from settings."""

from __future__ import annotations

from app.ai.provider import AIExplanationProvider, MockProvider
from app.ai.qualcomm import QualcommProvider
from app.config import get_qualcomm_settings, get_settings
from app.logging_config import get_logger
from app.models.ai import AIProviderStatus

log = get_logger("netmedic.ai")


def create_provider() -> AIExplanationProvider:
    settings = get_settings()
    if settings.ai_provider == "qualcomm":
        qualcomm = QualcommProvider(get_qualcomm_settings())
        if qualcomm.is_configured:
            log.info("[AI] Using Qualcomm Cloud AI Playground provider (model=%s)", qualcomm.settings.model)
            return qualcomm
        log.warning("[AI] NETMEDIC_AI_PROVIDER=qualcomm but QUALCOMM_AI_* variables are incomplete; using mock")
    return MockProvider()


def provider_status(provider: AIExplanationProvider) -> AIProviderStatus:
    settings = get_settings()
    model = getattr(getattr(provider, "settings", None), "model", None)
    if provider.name == "qualcomm":
        note = "Qualcomm Cloud AI Playground configured via environment; request shape is OpenAI-style chat completions (see app/ai/qualcomm.py)."
    elif settings.ai_provider == "qualcomm":
        note = "Qualcomm selected but not configured - set QUALCOMM_AI_BASE_URL, QUALCOMM_AI_API_KEY and QUALCOMM_AI_MODEL. Mock explanations in use."
    else:
        note = "Deterministic mock explanations generated from the structured diagnosis. Set NETMEDIC_AI_PROVIDER=qualcomm to enable the LLM."
    return AIProviderStatus(
        configured_provider=settings.ai_provider,
        active_provider=provider.name,
        model=model or None,
        ready=True,
        note=note,
    )
