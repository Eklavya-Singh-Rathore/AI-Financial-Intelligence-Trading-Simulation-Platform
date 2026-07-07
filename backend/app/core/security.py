"""API authentication (static API key) and in-process rate limiting.

Hardening stopgap per audit CRIT-1 until full authn/z (Phase 4/5):

* ``require_api_key`` - FastAPI dependency enforcing the ``X-API-Key`` header
  when ``API_KEY`` is configured. With no key configured (development), access
  is allowed and a warning is logged once at startup.
* ``RateLimitMiddleware`` - fixed-window per-client limiter. In-process only
  (each replica enforces its own window); adequate for the current
  single-process deployment, replace with a shared store when scaling out.
"""

from __future__ import annotations

import hmac
import threading
import time

import structlog
from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.core.config import get_settings

log = structlog.get_logger(__name__)

# Paths that never require auth or rate limiting (probes + docs).
OPEN_PATHS = frozenset({"/live", "/health", "/docs", "/redoc", "/openapi.json"})


async def require_api_key(request: Request) -> None:
    """Reject the request unless it carries the configured API key."""
    configured = get_settings().api_key
    if not configured:
        return  # auth disabled (development mode); warned at startup
    supplied = request.headers.get("x-api-key", "")
    if not hmac.compare_digest(supplied, configured):
        raise HTTPException(status_code=401, detail="invalid or missing API key")


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Fixed-window rate limiter keyed by client IP.

    Windows are per-minute; the counter dict is pruned each new window. Open
    paths (probes/docs) are exempt.
    """

    def __init__(self, app, limit_per_minute: int | None = None) -> None:
        super().__init__(app)
        self._limit = limit_per_minute
        self._lock = threading.Lock()
        self._window_start = 0
        self._counts: dict[str, int] = {}

    def _current_limit(self) -> int:
        if self._limit is not None:
            return self._limit
        return get_settings().rate_limit_per_minute

    def _check(self, key: str) -> bool:
        """Count a hit for ``key``; True if within limit."""
        now_window = int(time.time() // 60)
        with self._lock:
            if now_window != self._window_start:
                self._window_start = now_window
                self._counts = {}
            count = self._counts.get(key, 0) + 1
            self._counts[key] = count
            return count <= self._current_limit()

    async def dispatch(self, request: Request, call_next):
        if request.url.path in OPEN_PATHS:
            return await call_next(request)
        limit = self._current_limit()
        if limit <= 0:  # disabled
            return await call_next(request)
        client = request.client.host if request.client else "unknown"
        if not self._check(client):
            log.warning("rate_limited", client=client, path=request.url.path)
            return JSONResponse(
                status_code=429,
                content={"detail": "rate limit exceeded; retry later"},
                headers={"Retry-After": "60"},
            )
        return await call_next(request)


def warn_if_auth_disabled() -> None:
    """Log a prominent warning when running without an API key (startup)."""
    settings = get_settings()
    if not settings.api_key:
        log.warning(
            "api_auth_disabled",
            hint="set API_KEY in .env to require X-API-Key on all endpoints",
            env=settings.env,
        )
