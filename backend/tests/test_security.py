"""Tests for Phase 2.5 hardening: auth, rate limiting, probes, sanitization."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from app.api.routers.agents import _public_run, _RunGuard
from app.core.config import get_settings
from app.db.base import get_session
from app.main import app
from app.models.agent_run import AgentRun
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    async def _null_session():
        yield None

    # Hermetic premise: only what each test sets is configured (local .env may
    # otherwise enable Supabase user auth and turn open access into 401s).
    for key in ("API_KEY", "SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_JWT_SECRET"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "")
    get_settings.cache_clear()
    app.dependency_overrides[get_session] = _null_session
    try:
        # raise_server_exceptions=False: DB-touching routes 500 against the
        # null-session stub; these tests only assert auth/limit behaviour.
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()


@pytest.fixture
def with_api_key(monkeypatch):
    monkeypatch.setenv("API_KEY", "test-secret-key")
    get_settings.cache_clear()
    yield "test-secret-key"
    monkeypatch.delenv("API_KEY", raising=False)
    get_settings.cache_clear()


# --- probes -------------------------------------------------------------------

def test_live_probe_has_no_dependencies(client):
    r = client.get("/live")
    assert r.status_code == 200
    assert r.json() == {"status": "alive"}


def test_request_id_header_present(client):
    r = client.get("/live")
    assert r.headers.get("x-request-id")


def test_request_id_is_honoured(client):
    r = client.get("/live", headers={"X-Request-ID": "trace-me-123"})
    assert r.headers["x-request-id"] == "trace-me-123"


# --- API key auth ---------------------------------------------------------------

def test_auth_disabled_when_no_key_configured(client):
    # instruments requires a DB, but auth must not be the thing that rejects it
    r = client.get("/instruments")
    assert r.status_code != 401


def test_requests_rejected_without_key(client, with_api_key):
    r = client.get("/instruments")
    assert r.status_code == 401


def test_requests_accepted_with_key(client, with_api_key):
    r = client.get("/instruments", headers={"X-API-Key": with_api_key})
    assert r.status_code != 401


def test_probes_stay_open_with_key_configured(client, with_api_key):
    assert client.get("/live").status_code == 200
    assert client.get("/health").status_code == 200


def test_api_v1_alias_serves_routes(client):
    r = client.get("/api/v1/instruments")
    assert r.status_code != 404  # alias mounted (may 500 without DB, never 404)


# --- rate limiting --------------------------------------------------------------

def test_rate_limit_kicks_in(client, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "3")
    get_settings.cache_clear()
    try:
        statuses = [client.get("/instruments").status_code for _ in range(5)]
        assert 429 in statuses
        # probes exempt even while throttled
        assert client.get("/live").status_code == 200
    finally:
        monkeypatch.delenv("RATE_LIMIT_PER_MINUTE", raising=False)
        get_settings.cache_clear()


# --- run guard -------------------------------------------------------------------

def test_run_guard_caps_concurrency(monkeypatch):
    monkeypatch.setenv("MAX_CONCURRENT_AGENT_RUNS", "2")
    get_settings.cache_clear()
    try:
        guard = _RunGuard()
        assert guard.try_acquire() and guard.try_acquire()
        assert not guard.try_acquire()
        guard.release()
        assert guard.try_acquire()
    finally:
        monkeypatch.delenv("MAX_CONCURRENT_AGENT_RUNS", raising=False)
        get_settings.cache_clear()


# --- error sanitization -----------------------------------------------------------

def _run_with_error(error: str) -> AgentRun:
    return AgentRun(
        id=uuid.uuid4(),
        instrument_id=uuid.uuid4(),
        symbol="X",
        status="failed",
        trigger="api",
        debate_rounds=1,
        error=error,
        created_at=datetime.now(UTC),
    )


def test_internal_error_text_is_hidden_by_default():
    out = _public_run(_run_with_error("Traceback: secret /etc/creds path leak"))
    assert "secret" not in (out.error or "")
    assert "details in server logs" in (out.error or "")


def test_curated_errors_pass_through():
    out = _public_run(_run_with_error("run timed out after 600s"))
    assert out.error == "run timed out after 600s"
    orphan_msg = "orphaned: no worker attached after restart (startup sweep)"
    out2 = _public_run(_run_with_error(orphan_msg))
    assert (out2.error or "").startswith("orphaned")


def test_full_errors_exposed_when_enabled(monkeypatch):
    monkeypatch.setenv("EXPOSE_ERROR_DETAILS", "true")
    get_settings.cache_clear()
    try:
        out = _public_run(_run_with_error("raw internal detail"))
        assert out.error == "raw internal detail"
    finally:
        monkeypatch.delenv("EXPOSE_ERROR_DETAILS", raising=False)
        get_settings.cache_clear()
