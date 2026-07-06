"""LLM client construction + primary→fallback failover.

The active provider chain comes from settings (``LLM_PROVIDER``,
``LLM_FALLBACK_PROVIDER``) so switching providers is a config change only.
"""

from __future__ import annotations

import structlog

from app.core.config import Settings, get_settings
from app.llm.base import LLMClient, LLMError, LLMResponse, Message
from app.llm.fake_client import FakeLLMClient

log = structlog.get_logger(__name__)

PROVIDERS = ("gemini", "openai", "fake")


class FailoverLLMClient(LLMClient):
    """Try the primary provider (with one retry), then fall back."""

    def __init__(self, primary: LLMClient, fallback: LLMClient | None) -> None:
        self.primary = primary
        self.fallback = fallback
        self.provider = primary.provider

    def complete(
        self,
        system: str,
        messages: list[Message],
        json_schema: dict | None = None,
    ) -> LLMResponse:
        last_error: LLMError | None = None
        for attempt in (1, 2):
            try:
                return self.primary.complete(system, messages, json_schema)
            except LLMError as exc:
                last_error = exc
                log.warning(
                    "llm_primary_failed",
                    provider=self.primary.provider,
                    attempt=attempt,
                    error=str(exc),
                )
        if self.fallback is not None:
            log.warning(
                "llm_failover",
                from_provider=self.primary.provider,
                to_provider=self.fallback.provider,
            )
            return self.fallback.complete(system, messages, json_schema)
        assert last_error is not None
        raise last_error


def _build_single(name: str, settings: Settings) -> LLMClient:
    resolved = name.strip().lower()
    if resolved == "gemini":
        from app.llm.gemini_client import GeminiClient

        return GeminiClient(
            api_key=settings.google_ai_studio_api_key or "",
            model=settings.gemini_model,
            timeout_seconds=settings.llm_timeout_seconds,
        )
    if resolved == "openai":
        from app.llm.openai_client import OpenAIClient

        return OpenAIClient(
            api_key=settings.openai_api_key or "",
            model=settings.openai_model,
            timeout_seconds=settings.llm_timeout_seconds,
        )
    if resolved == "fake":
        return FakeLLMClient()
    raise ValueError(f"unknown LLM provider '{name}'. Available: {', '.join(PROVIDERS)}")


def get_llm_client(settings: Settings | None = None) -> LLMClient:
    """Build the configured client chain (primary + optional fallback)."""
    settings = settings or get_settings()
    primary = _build_single(settings.llm_provider, settings)
    fallback: LLMClient | None = None
    fb_name = (settings.llm_fallback_provider or "").strip()
    if fb_name and fb_name.lower() != settings.llm_provider.strip().lower():
        try:
            fallback = _build_single(fb_name, settings)
        except (LLMError, ValueError) as exc:
            log.warning("llm_fallback_unavailable", provider=fb_name, error=str(exc))
    return FailoverLLMClient(primary, fallback)
