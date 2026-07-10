"""Authentication & authorization (Phase 4).

Two credential types, one dependency:

* ``X-API-Key`` (static, from settings) -> role ``service``. Admin-equivalent;
  used by automation, tests, and the frontend proxy's local-dev fallback.
  Preserves every pre-Phase-4 API behavior.
* ``Authorization: Bearer <supabase-jwt>`` -> an authenticated user. Verified
  LOCALLY (HS256 via SUPABASE_JWT_SECRET) when the secret is configured,
  otherwise REMOTELY against ``{SUPABASE_URL}/auth/v1/user`` with a short TTL
  cache so deployment never blocks on the dashboard-only JWT secret.

Roles: ``service`` (API key) > ``admin`` (JWT app_metadata.role == 'admin',
granted by the auth.users trigger for the owner emails) > ``user`` (default).
``admin`` and ``service`` see all rows; ``user`` sees only rows they own.

With NEITHER api_key NOR supabase configured (bare local dev), requests get an
anonymous service context - current dev behavior, loudly warned at startup.
"""

from __future__ import annotations

import hashlib
import hmac
import threading
import time
import uuid
from dataclasses import dataclass

import httpx
import structlog
from fastapi import HTTPException, Request

from app.core.config import Settings, get_settings

log = structlog.get_logger(__name__)

_REMOTE_CACHE_TTL_SECONDS = 60.0
_remote_cache: dict[str, tuple[float, AuthContext]] = {}
_remote_cache_lock = threading.Lock()

PRIVILEGED_ROLES = ("admin", "service")


@dataclass(frozen=True)
class AuthContext:
    """Resolved identity of the caller."""

    user_id: uuid.UUID | None  # None for service/anonymous contexts
    role: str  # user | admin | service
    via: str  # api_key | jwt | jwt_remote | anonymous
    email: str | None = None

    @property
    def privileged(self) -> bool:
        return self.role in PRIVILEGED_ROLES

    def owner_filter_id(self) -> uuid.UUID | None:
        """user_id to filter queries by; None means 'no filter' (privileged)."""
        return None if self.privileged else self.user_id


def _auth_configured(settings: Settings) -> bool:
    return bool(settings.api_key or (settings.supabase_url and settings.supabase_anon_key))


def _context_from_claims(claims: dict, via: str) -> AuthContext:
    sub = claims.get("sub")
    try:
        user_id = uuid.UUID(str(sub))
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=401, detail="invalid token subject") from exc
    app_meta = claims.get("app_metadata") or {}
    role = str(app_meta.get("role") or "user").lower()
    if role not in ("user", "admin"):
        role = "user"
    return AuthContext(user_id=user_id, role=role, via=via, email=claims.get("email"))


def _verify_jwt_local(token: str, settings: Settings) -> AuthContext:
    import jwt as pyjwt

    try:
        claims = pyjwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
            options={"require": ["exp", "sub"]},
        )
    except pyjwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail=f"invalid token: {exc}") from exc
    return _context_from_claims(claims, via="jwt")


def _verify_jwt_remote(token: str, settings: Settings) -> AuthContext:
    """Validate the token by asking Supabase Auth who it belongs to (cached)."""
    digest = hashlib.sha256(token.encode()).hexdigest()
    now = time.monotonic()
    with _remote_cache_lock:
        hit = _remote_cache.get(digest)
        if hit and now - hit[0] < _REMOTE_CACHE_TTL_SECONDS:
            return hit[1]

    try:
        response = httpx.get(
            f"{settings.supabase_url.rstrip('/')}/auth/v1/user",
            headers={
                "Authorization": f"Bearer {token}",
                "apikey": settings.supabase_anon_key,
            },
            timeout=10.0,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="auth service unreachable") from exc
    if response.status_code != 200:
        raise HTTPException(status_code=401, detail="invalid or expired token")

    body = response.json()
    claims = {
        "sub": body.get("id"),
        "app_metadata": body.get("app_metadata"),
        "email": body.get("email"),
    }
    ctx = _context_from_claims(claims, via="jwt_remote")
    with _remote_cache_lock:
        if len(_remote_cache) > 512:  # bounded cache
            _remote_cache.clear()
        _remote_cache[digest] = (now, ctx)
    return ctx


async def get_auth(request: Request) -> AuthContext:
    """FastAPI dependency resolving the caller's identity (or raising 401)."""
    settings = get_settings()

    supplied_key = request.headers.get("x-api-key", "")
    if settings.api_key and supplied_key:
        if hmac.compare_digest(supplied_key, settings.api_key):
            return AuthContext(user_id=None, role="service", via="api_key")
        raise HTTPException(status_code=401, detail="invalid API key")

    authz = request.headers.get("authorization", "")
    if authz.lower().startswith("bearer "):
        token = authz[7:].strip()
        if not (settings.supabase_url and settings.supabase_anon_key):
            raise HTTPException(status_code=401, detail="user auth not configured")
        if settings.supabase_jwt_secret:
            return _verify_jwt_local(token, settings)
        return _verify_jwt_remote(token, settings)

    if not _auth_configured(settings):
        return AuthContext(user_id=None, role="service", via="anonymous")
    raise HTTPException(
        status_code=401,
        detail="authentication required (Bearer token or X-API-Key)",
    )


def warn_if_user_auth_disabled() -> None:
    settings = get_settings()
    if not (settings.supabase_url and settings.supabase_anon_key):
        log.warning(
            "user_auth_disabled",
            hint="set SUPABASE_URL + SUPABASE_ANON_KEY to enable Bearer-JWT user auth",
        )
