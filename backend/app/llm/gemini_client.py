"""Google AI Studio (Gemini) client via the google-genai SDK."""

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


class GeminiClient(LLMClient):
    provider = "gemini"

    def __init__(self, api_key: str, model: str, timeout_seconds: float = 90.0) -> None:
        if not api_key:
            raise LLMError("GOOGLE_AI_STUDIO_API_KEY is not configured")
        # Lazy import so the package is only required when actually used.
        from google import genai

        self._genai = genai
        self._client = genai.Client(
            api_key=api_key,
            http_options={"timeout": int(timeout_seconds * 1000)},  # milliseconds
        )
        self.model = model

    def complete(
        self,
        system: str,
        messages: list[Message],
        json_schema: dict | None = None,
    ) -> LLMResponse:
        from google.genai import types

        system_prompt = system + (schema_instruction(json_schema) if json_schema else "")
        contents = [
            types.Content(
                role="user" if m["role"] == "user" else "model",
                parts=[types.Part.from_text(text=m["content"])],
            )
            for m in messages
        ]
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json" if json_schema else None,
        )

        started = time.perf_counter()
        try:
            response = self._client.models.generate_content(
                model=self.model, contents=contents, config=config
            )
        except Exception as exc:  # noqa: BLE001 - normalize provider errors
            raise LLMError(f"gemini request failed: {exc}") from exc
        latency_ms = int((time.perf_counter() - started) * 1000)

        text = response.text or ""
        if not text.strip():
            raise LLMError("gemini returned an empty response")

        usage: dict[str, int] = {}
        meta = getattr(response, "usage_metadata", None)
        if meta is not None:
            usage = {
                "input_tokens": int(getattr(meta, "prompt_token_count", 0) or 0),
                "output_tokens": int(getattr(meta, "candidates_token_count", 0) or 0),
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
