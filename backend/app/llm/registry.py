"""LLM client construction + primary→fallback failover.

The active provider chain comes from settings (``LLM_PROVIDER``,
``LLM_FALLBACK_PROVIDER``) so switching providers is a config change only.
"""

from __future__ import annotations

import random
import time

import structlog

from app.core.config import Settings, get_settings
from app.llm.base import LLMClient, LLMError, LLMResponse, Message
from app.llm.fake_client import FakeLLMClient

log = structlog.get_logger(__name__)

PROVIDERS = ("gemini", "openai", "fake")

_MAX_ATTEMPTS = 2
_BACKOFF_BASE_SECONDS = 1.5


class FailoverLLMClient(LLMClient):
    """Primary with classified retry + backoff, then fallback.

    * Any exception (LLMError or foreign) is normalized to LLMError.
    * Non-retryable errors (auth/quota/bad request) skip the retry and go
      straight to the fallback (audit HIGH-1 / MED-10).
    * Retries back off with jitter (this client runs in a worker thread, so
      ``time.sleep`` is safe).
    """

    def __init__(self, primary: LLMClient, fallback: LLMClient | None) -> None:
        self.primary = primary
        self.fallback = fallback
        self.provider = primary.provider

    @staticmethod
    def _call(
        client: LLMClient, system: str, messages: list[Message], schema: dict | None
    ) -> LLMResponse:
        try:
            return client.complete(system, messages, schema)
        except LLMError:
            raise
        except Exception as exc:  # noqa: BLE001 - belt-and-braces normalization
            raise LLMError(f"{client.provider} raised {type(exc).__name__}: {exc}") from exc

    def complete(
        self,
        system: str,
        messages: list[Message],
        json_schema: dict | None = None,
    ) -> LLMResponse:
        last_error: LLMError | None = None
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                return self._call(self.primary, system, messages, json_schema)
            except LLMError as exc:
                last_error = exc
                log.warning(
                    "llm_primary_failed",
                    provider=self.primary.provider,
                    attempt=attempt,
                    retryable=exc.retryable,
                    error=str(exc)[:300],
                )
                if not exc.retryable:
                    break  # retrying cannot help; go to fallback
                if attempt < _MAX_ATTEMPTS:
                    time.sleep(_BACKOFF_BASE_SECONDS * attempt + random.uniform(0, 0.5))
        if self.fallback is not None:
            log.warning(
                "llm_failover",
                from_provider=self.primary.provider,
                to_provider=self.fallback.provider,
            )
            return self._call(self.fallback, system, messages, json_schema)
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
