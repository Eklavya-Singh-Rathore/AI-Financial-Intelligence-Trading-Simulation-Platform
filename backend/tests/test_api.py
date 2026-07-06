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
def client():
    app.dependency_overrides[get_session] = _null_session
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.clear()


def test_health_without_database(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["database"] == "not_configured"


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
    }
    assert expected <= set(paths)


def test_forecast_horizon_validation(client):
    r = client.get("/instruments/RELIANCE/forecast?horizon=0")
    assert r.status_code == 422


def test_backtest_body_validation(client):
    # negative initial_cash must be rejected by the schema before any DB access
    r = client.post("/backtest", json={"symbol": "RELIANCE", "initial_cash": -5})
    assert r.status_code == 422
