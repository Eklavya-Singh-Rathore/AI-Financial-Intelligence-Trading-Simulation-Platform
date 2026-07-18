"""API tests that need no database (app boot, health, validation errors)."""

from __future__ import annotations

import pytest
from app.db.base import get_session
from app.main import app
from fastapi.testclient import TestClient


async def _null_session():
    """Stub session dependency: these tests must fail validation before any DB use."""
    yield None


@pytest.fixture
def client(monkeypatch):
    # Hermetic premise: NO auth configured (the local .env may set Supabase auth).
    from app.core.config import get_settings

    for key in ("API_KEY", "SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_JWT_SECRET"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "")
    get_settings.cache_clear()
    app.dependency_overrides[get_session] = _null_session
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()


def test_health_without_database(client, monkeypatch):
    from app.core.config import get_settings

    # Force the not-configured state regardless of the local .env.
    monkeypatch.setenv("DATABASE_URL", "")
    get_settings.cache_clear()
    try:
        r = client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert body["database"] == "not_configured"
        # Phase 6 Kronos audit: /health surfaces the configured checkpoint ids.
        assert body["kronos_model_id"] == "NeoQuasar/Kronos-small"
        assert body["kronos_tokenizer_id"] == "NeoQuasar/Kronos-Tokenizer-base"
        assert body["default_forecaster"] == "kronos"
        assert body["kronos_max_context"] == 512
        # local mode (test default) → no remote_inference block
        assert "remote_inference" not in body
    finally:
        monkeypatch.delenv("DATABASE_URL", raising=False)
        get_settings.cache_clear()


def test_health_remote_reports_cached_space_health(client, monkeypatch):
    from app.core.config import get_settings
    from app.services import space_client

    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("KRONOS_MODE", "remote")
    monkeypatch.setenv("INFERENCE_SPACE_URL", "https://example.test")
    get_settings.cache_clear()
    space_client.reset_space_client()
    # Simulate the keepalive job having cached a Space /health payload.
    space_client.get_space_client().last_health = {
        "kronos_model_id": "NeoQuasar/Kronos-small",
        "kronos_tokenizer_id": "NeoQuasar/Kronos-Tokenizer-base",
        "embedding_model_id": "all-MiniLM-L6-v2",
        "device": "cpu",
        "app_version": "0.2.3",
    }
    try:
        body = client.get("/health").json()
        assert body["kronos_mode"] == "remote"
        assert body["remote_inference"]["kronos_model_id"] == "NeoQuasar/Kronos-small"
        assert body["remote_inference"]["device"] == "cpu"
    finally:
        for key in ("DATABASE_URL", "KRONOS_MODE", "INFERENCE_SPACE_URL"):
            monkeypatch.delenv(key, raising=False)
        get_settings.cache_clear()
        space_client.reset_space_client()


def test_openapi_lists_all_endpoints(client):
    paths = client.get("/openapi.json").json()["paths"]
    expected = {
        "/health",
        "/instruments",
        "/instruments/{symbol}/prices",
        "/instruments/{symbol}/indicators",
        "/instruments/{symbol}/forecast",
        "/backtest",
        "/ingest/run",
        "/agents/run",
        "/agents/runs",
        "/agents/runs/{run_id}",
        "/agents/runs/{run_id}/messages",
    }
    assert expected <= set(paths)


def test_agents_run_body_validation(client):
    # debate_rounds out of range must 422 before any DB access
    r = client.post("/agents/run", json={"symbol": "RELIANCE", "debate_rounds": 9})
    assert r.status_code == 422


def test_forecast_horizon_validation(client):
    r = client.get("/instruments/RELIANCE/forecast?horizon=0")
    assert r.status_code == 422


def test_backtest_body_validation(client):
    # negative initial_cash must be rejected by the schema before any DB access
    r = client.post("/backtest", json={"symbol": "RELIANCE", "initial_cash": -5})
    assert r.status_code == 422
