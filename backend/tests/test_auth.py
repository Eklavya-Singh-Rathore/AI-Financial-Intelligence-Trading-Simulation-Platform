"""Tests for the Phase 4 auth core (API key, JWT local/remote, roles). No network."""

from __future__ import annotations

import time
import uuid

import jwt as pyjwt
import pytest
from app.core import auth as auth_mod
from app.core.auth import AuthContext, get_auth
from app.core.config import get_settings
from starlette.requests import Request

SECRET = "test-jwt-secret"
USER_ID = str(uuid.uuid4())


def _request(headers: dict[str, str] | None = None) -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    return Request({"type": "http", "method": "GET", "path": "/x", "headers": raw})


def _token(role: str | None = None, *, exp_delta: int = 3600, secret: str = SECRET) -> str:
    claims: dict = {
        "sub": USER_ID,
        "aud": "authenticated",
        "exp": int(time.time()) + exp_delta,
        "email": "u@example.com",
    }
    if role:
        claims["app_metadata"] = {"role": role}
    return pyjwt.encode(claims, secret, algorithm="HS256")


@pytest.fixture
def jwt_env(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", SECRET)
    get_settings.cache_clear()
    yield
    for key in ("SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_JWT_SECRET"):
        monkeypatch.delenv(key, raising=False)
    get_settings.cache_clear()


async def test_api_key_grants_service_role(monkeypatch):
    monkeypatch.setenv("API_KEY", "svc-key")
    get_settings.cache_clear()
    try:
        ctx = await get_auth(_request({"X-API-Key": "svc-key"}))
        assert ctx.role == "service" and ctx.privileged and ctx.user_id is None
        assert ctx.owner_filter_id() is None
    finally:
        monkeypatch.delenv("API_KEY", raising=False)
        get_settings.cache_clear()


async def test_wrong_api_key_rejected(monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setenv("API_KEY", "svc-key")
    get_settings.cache_clear()
    try:
        with pytest.raises(HTTPException) as exc:
            await get_auth(_request({"X-API-Key": "nope"}))
        assert exc.value.status_code == 401
    finally:
        monkeypatch.delenv("API_KEY", raising=False)
        get_settings.cache_clear()


async def test_jwt_local_verification(jwt_env):
    ctx = await get_auth(_request({"Authorization": f"Bearer {_token()}"}))
    assert str(ctx.user_id) == USER_ID
    assert ctx.role == "user" and not ctx.privileged
    assert ctx.owner_filter_id() == ctx.user_id
    assert ctx.via == "jwt"


async def test_jwt_admin_role_from_app_metadata(jwt_env):
    ctx = await get_auth(_request({"Authorization": f"Bearer {_token('admin')}"}))
    assert ctx.role == "admin" and ctx.privileged
    assert ctx.owner_filter_id() is None


async def test_jwt_expired_rejected(jwt_env):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await get_auth(_request({"Authorization": f"Bearer {_token(exp_delta=-100)}"}))
    assert exc.value.status_code == 401


async def test_jwt_wrong_secret_rejected(jwt_env):
    from fastapi import HTTPException

    bad = _token(secret="other-secret")
    with pytest.raises(HTTPException) as exc:
        await get_auth(_request({"Authorization": f"Bearer {bad}"}))
    assert exc.value.status_code == 401


async def test_missing_credentials_rejected_when_auth_configured(jwt_env):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await get_auth(_request())
    assert exc.value.status_code == 401


async def test_anonymous_service_when_nothing_configured(monkeypatch):
    # setenv("") overrides the local .env file (delenv alone would not).
    for key in ("API_KEY", "SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_JWT_SECRET"):
        monkeypatch.setenv(key, "")
    get_settings.cache_clear()
    try:
        ctx = await get_auth(_request())
        assert ctx.role == "service" and ctx.via == "anonymous"
    finally:
        get_settings.cache_clear()


async def test_remote_verification_and_cache(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)
    get_settings.cache_clear()
    auth_mod._remote_cache.clear()

    calls = {"n": 0}

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"id": USER_ID, "email": "u@example.com", "app_metadata": {"role": "admin"}}

    def fake_get(url, headers=None, timeout=None):
        calls["n"] += 1
        assert url.endswith("/auth/v1/user")
        return FakeResponse()

    monkeypatch.setattr(auth_mod.httpx, "get", fake_get)
    try:
        req = _request({"Authorization": "Bearer remote-token"})
        ctx1 = await get_auth(req)
        ctx2 = await get_auth(req)  # served from the TTL cache
        assert str(ctx1.user_id) == USER_ID and ctx1.role == "admin"
        assert ctx1.via == "jwt_remote"
        assert ctx2.role == "admin"
        assert calls["n"] == 1
    finally:
        for key in ("SUPABASE_URL", "SUPABASE_ANON_KEY"):
            monkeypatch.delenv(key, raising=False)
        get_settings.cache_clear()
        auth_mod._remote_cache.clear()


def test_context_helpers():
    svc = AuthContext(user_id=None, role="service", via="api_key")
    usr = AuthContext(user_id=uuid.uuid4(), role="user", via="jwt")
    adm = AuthContext(user_id=uuid.uuid4(), role="admin", via="jwt")
    assert svc.privileged and adm.privileged and not usr.privileged
    assert svc.owner_filter_id() is None and adm.owner_filter_id() is None
    assert usr.owner_filter_id() == usr.user_id
