"""Deterministic fake LLM for tests - no network, canned or rule-based replies.

``FakeLLMClient`` returns queued responses in order, or a schema-aware default
when the queue is empty (so full-pipeline tests run without scripting every
call). It records every request for assertions.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

from app.llm.base import LLMClient, LLMResponse, Message, parse_json_text


@dataclass
class RecordedCall:
    system: str
    messages: list[Message]
    json_schema: dict | None


def _default_for_schema(schema: dict) -> dict:
    """Build a minimal valid object for a flat JSON schema (test default)."""
    out: dict = {}
    for name, spec in (schema.get("properties") or {}).items():
        t = spec.get("type")
        if "enum" in spec:
            out[name] = spec["enum"][0]
        elif t == "number":
            out[name] = 0.5
        elif t == "integer":
            out[name] = 1
        elif t == "boolean":
            out[name] = True
        elif t == "array":
            out[name] = []
        else:
            out[name] = f"fake {name}"
    return out


@dataclass
class FakeLLMClient(LLMClient):
    provider = "fake"
    model: str = "fake-1"
    responses: list[str] = field(default_factory=list)  # consumed FIFO
    fail_times: int = 0  # raise LLMError for the first N calls (failover tests)
    calls: list[RecordedCall] = field(default_factory=list)

    def complete(
        self,
        system: str,
        messages: list[Message],
        json_schema: dict | None = None,
    ) -> LLMResponse:
        from app.llm.base import LLMError

        self.calls.append(RecordedCall(system=system, messages=messages, json_schema=json_schema))
        if self.fail_times > 0:
            self.fail_times -= 1
            raise LLMError("fake provider failure (scripted)")

        if self.responses:
            text = self.responses.pop(0)
        elif json_schema is not None:
            text = json.dumps(_default_for_schema(json_schema))
        else:
            text = "fake response"

        # time.time_ns is monotonic enough for a fake latency value.
        _ = time.time_ns()
        parsed = parse_json_text(text) if json_schema else None
        return LLMResponse(
            text=text, provider=self.provider, model=self.model,
            latency_ms=1, usage={"input_tokens": 10, "output_tokens": 5}, parsed=parsed,
        )
