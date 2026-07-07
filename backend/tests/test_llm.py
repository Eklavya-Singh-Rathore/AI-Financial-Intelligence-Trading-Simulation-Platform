"""Unit tests for the LLM layer (parsing, fake client, failover). No network."""

from __future__ import annotations

import json

import pytest
from app.core.config import Settings
from app.llm.base import LLMError, parse_json_text
from app.llm.fake_client import FakeLLMClient
from app.llm.registry import FailoverLLMClient, get_llm_client

SCHEMA = {
    "type": "object",
    "properties": {
        "stance": {"type": "string", "enum": ["bullish", "bearish", "neutral"]},
        "confidence": {"type": "number"},
        "summary": {"type": "string"},
    },
    "required": ["stance", "confidence", "summary"],
}


# --- parse_json_text ---------------------------------------------------------

def test_parse_plain_json():
    assert parse_json_text('{"a": 1}') == {"a": 1}


def test_parse_fenced_json():
    text = 'Here you go:\n```json\n{"a": 1, "b": [2, 3]}\n```\nthanks'
    assert parse_json_text(text) == {"a": 1, "b": [2, 3]}


def test_parse_embedded_object():
    assert parse_json_text('noise {"a": {"b": 2}} trailing') == {"a": {"b": 2}}


def test_parse_garbage_raises():
    with pytest.raises(LLMError):
        parse_json_text("no json here at all")


# --- FakeLLMClient ------------------------------------------------------------

def test_fake_queued_responses_fifo():
    fake = FakeLLMClient(responses=['{"x": 1}', '{"x": 2}'])
    r1 = fake.complete("s", [{"role": "user", "content": "m"}], {"type": "object"})
    r2 = fake.complete("s", [{"role": "user", "content": "m"}], {"type": "object"})
    assert (r1.parsed, r2.parsed) == ({"x": 1}, {"x": 2})
    assert len(fake.calls) == 2


def test_fake_schema_default_is_valid():
    fake = FakeLLMClient()
    r = fake.complete("s", [{"role": "user", "content": "m"}], SCHEMA)
    assert r.parsed is not None
    assert r.parsed["stance"] == "bullish"  # first enum value
    assert isinstance(r.parsed["confidence"], float)
    # round-trips as JSON
    json.dumps(r.parsed)


# --- Failover -----------------------------------------------------------------

def test_failover_uses_fallback_after_primary_fails_twice(monkeypatch):
    monkeypatch.setattr("app.llm.registry.time.sleep", lambda _s: None)
    primary = FakeLLMClient(fail_times=2)
    primary.provider = "gemini"
    fallback = FakeLLMClient(responses=['{"ok": true}'])
    fallback.provider = "openai"
    client = FailoverLLMClient(primary, fallback)
    r = client.complete("s", [{"role": "user", "content": "m"}], {"type": "object"})
    assert r.provider == "openai"
    assert r.parsed == {"ok": True}
    assert len(primary.calls) == 2  # one attempt + one retry


def test_primary_retry_succeeds_without_fallback_call(monkeypatch):
    monkeypatch.setattr("app.llm.registry.time.sleep", lambda _s: None)
    primary = FakeLLMClient(fail_times=1, responses=['{"ok": 1}'])
    fallback = FakeLLMClient()
    client = FailoverLLMClient(primary, fallback)
    r = client.complete("s", [{"role": "user", "content": "m"}], {"type": "object"})
    assert r.provider == "fake"
    assert len(fallback.calls) == 0


def test_failover_raises_when_no_fallback(monkeypatch):
    monkeypatch.setattr("app.llm.registry.time.sleep", lambda _s: None)
    primary = FakeLLMClient(fail_times=2)
    client = FailoverLLMClient(primary, None)
    with pytest.raises(LLMError):
        client.complete("s", [{"role": "user", "content": "m"}])


# --- Phase 2.5: error classification + failover coverage ------------------------

def test_llm_error_classification():
    assert LLMError("HTTP 500 upstream broke").retryable is True
    assert LLMError("rate limited, please slow down").retryable is True
    assert LLMError("Error 429: insufficient_quota, check billing").retryable is False
    assert LLMError("401 unauthorized").retryable is False
    assert LLMError("API key not valid").retryable is False
    assert LLMError("anything", retryable=True).retryable is True


def test_non_retryable_error_skips_retry_and_fails_over(monkeypatch):
    monkeypatch.setattr("app.llm.registry.time.sleep", lambda _s: None)

    class QuotaDead(FakeLLMClient):
        def complete(self, system, messages, json_schema=None):
            self.calls.append(None)
            raise LLMError("429 insufficient_quota")

    primary = QuotaDead()
    primary.provider = "openai"
    fallback = FakeLLMClient(responses=['{"ok": 2}'])
    client = FailoverLLMClient(primary, fallback)
    r = client.complete("s", [{"role": "user", "content": "m"}], {"type": "object"})
    assert r.parsed == {"ok": 2}
    assert len(primary.calls) == 1  # NO second attempt on non-retryable


def test_foreign_exceptions_are_normalized_and_fail_over(monkeypatch):
    """HIGH-1: a ValueError from a provider must still reach the fallback."""
    monkeypatch.setattr("app.llm.registry.time.sleep", lambda _s: None)

    class Weird(FakeLLMClient):
        def complete(self, system, messages, json_schema=None):
            raise ValueError("response has no parts")

    primary = Weird()
    primary.provider = "gemini"
    fallback = FakeLLMClient(responses=['{"ok": 3}'])
    client = FailoverLLMClient(primary, fallback)
    r = client.complete("s", [{"role": "user", "content": "m"}], {"type": "object"})
    assert r.parsed == {"ok": 3}


# --- Registry ------------------------------------------------------------------

def _settings(**kwargs) -> Settings:
    return Settings(_env_file=None, **kwargs)


def test_registry_fake_provider_no_keys_needed():
    client = get_llm_client(_settings(llm_provider="fake", llm_fallback_provider=None))
    assert client.provider == "fake"


def test_registry_missing_fallback_key_degrades_gracefully():
    # openai fallback has no key -> chain still builds with primary only
    client = get_llm_client(
        _settings(llm_provider="fake", llm_fallback_provider="openai", openai_api_key=None)
    )
    assert isinstance(client, FailoverLLMClient)
    assert client.fallback is None


def test_registry_unknown_provider():
    with pytest.raises(ValueError, match="unknown LLM provider"):
        get_llm_client(_settings(llm_provider="llama9000"))
