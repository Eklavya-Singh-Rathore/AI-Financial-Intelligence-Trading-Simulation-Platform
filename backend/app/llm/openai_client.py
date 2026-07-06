"""OpenAI client (fallback provider) via the official openai SDK."""

from __future__ import annotations

import time

import structlog

from app.llm.base import (
    LLMClient,
    LLMError,
    LLMResponse,
    Message,
    parse_json_text,
    schema_instruction,
)

log = structlog.get_logger(__name__)


class OpenAIClient(LLMClient):
    provider = "openai"

    def __init__(self, api_key: str, model: str, timeout_seconds: float = 90.0) -> None:
        if not api_key:
            raise LLMError("OPENAI_API_KEY is not configured")
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key, timeout=timeout_seconds, max_retries=1)
        self.model = model

    def complete(
        self,
        system: str,
        messages: list[Message],
        json_schema: dict | None = None,
    ) -> LLMResponse:
        system_prompt = system + (schema_instruction(json_schema) if json_schema else "")
        chat_messages: list = [{"role": "system", "content": system_prompt}] + [
            {"role": m["role"], "content": m["content"]} for m in messages
        ]

        kwargs: dict = {}
        if json_schema:
            kwargs["response_format"] = {"type": "json_object"}

        started = time.perf_counter()
        try:
            response = self._client.chat.completions.create(
                model=self.model, messages=chat_messages, **kwargs
            )
        except Exception as exc:  # noqa: BLE001 - normalize provider errors
            raise LLMError(f"openai request failed: {exc}") from exc
        latency_ms = int((time.perf_counter() - started) * 1000)

        text = (response.choices[0].message.content or "") if response.choices else ""
        if not text.strip():
            raise LLMError("openai returned an empty response")

        usage: dict[str, int] = {}
        if response.usage is not None:
            usage = {
                "input_tokens": int(response.usage.prompt_tokens or 0),
                "output_tokens": int(response.usage.completion_tokens or 0),
            }

        parsed = parse_json_text(text) if json_schema else None
        log.info(
            "llm_call", provider=self.provider, model=self.model,
            latency_ms=latency_ms, **usage,
        )
        return LLMResponse(
            text=text, provider=self.provider, model=self.model,
            latency_ms=latency_ms, usage=usage, parsed=parsed,
        )
