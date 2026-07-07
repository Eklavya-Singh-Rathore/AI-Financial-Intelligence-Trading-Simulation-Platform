"""LLM client interface shared by all providers (Gemini, OpenAI, fake).

Design notes:
* Clients are **synchronous**; async callers wrap them in ``asyncio.to_thread``.
  This keeps providers trivially testable and avoids double event-loop plumbing.
* When ``json_schema`` is passed, providers enable their native JSON mode and the
  schema is appended to the system prompt; :func:`parse_json_text` extracts the
  object. Strict validation happens at the caller (pydantic models per agent).
* Every response carries token usage + latency for cost tracking.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

Message = dict[str, str]  # {"role": "user"|"assistant", "content": str}

# Error-message fragments that indicate retrying the same provider is pointless
# (bad credentials, exhausted quota, malformed request).
_NON_RETRYABLE_MARKERS = (
    "insufficient_quota",
    "invalid api key",
    "api key not valid",
    "api_key",
    "permission",
    "unauthorized",
    "401",
    "403",
    "400",
)


class LLMError(RuntimeError):
    """Raised when a provider cannot produce a completion.

    ``retryable=False`` marks failures where retrying the same provider cannot
    help (auth/quota/bad request); failover should skip straight to the
    fallback provider.
    """

    def __init__(self, message: str, *, retryable: bool | None = None) -> None:
        super().__init__(message)
        if retryable is None:
            lowered = message.lower()
            retryable = not any(marker in lowered for marker in _NON_RETRYABLE_MARKERS)
        self.retryable = retryable


@dataclass
class LLMResponse:
    text: str
    provider: str
    model: str
    latency_ms: int
    usage: dict[str, int] = field(default_factory=dict)  # input_tokens/output_tokens
    parsed: dict | list | None = None  # populated when json_schema was requested


class LLMClient(ABC):
    """Minimal completion interface used by all agents."""

    provider: str = "base"

    @abstractmethod
    def complete(
        self,
        system: str,
        messages: list[Message],
        json_schema: dict | None = None,
    ) -> LLMResponse:
        raise NotImplementedError


def schema_instruction(json_schema: dict) -> str:
    """Render a JSON-schema directive appended to the system prompt."""
    return (
        "\n\nRespond ONLY with a single valid JSON object (no markdown fences, no "
        "commentary) conforming to this JSON schema:\n"
        + json.dumps(json_schema, indent=2)
    )


_JSON_BLOCK = re.compile(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", re.DOTALL)


def parse_json_text(text: str) -> dict | list:
    """Parse a JSON object out of an LLM response, tolerating code fences."""
    candidate = text.strip()
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass
    match = _JSON_BLOCK.search(candidate)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    # Last resort: first {...} span.
    start, end = candidate.find("{"), candidate.rfind("}")
    if 0 <= start < end:
        try:
            return json.loads(candidate[start : end + 1])
        except json.JSONDecodeError:
            pass
    raise LLMError(f"model did not return parseable JSON: {text[:200]!r}")
