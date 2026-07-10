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
    finally:
        monkeypatch.delenv("DATABASE_URL", raising=False)
        get_settings.cache_clear()


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
