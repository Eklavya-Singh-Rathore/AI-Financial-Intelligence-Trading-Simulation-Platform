"""FastAPI application entrypoint.

Run locally with:
    uvicorn app.main:app --reload   (from the backend/ directory)
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routers import agents, backtest, health, ingest, instruments
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.middleware import RequestIDMiddleware
from app.core.security import RateLimitMiddleware, require_api_key, warn_if_auth_disabled
from app.db.base import dispose_engine
from app.scheduler.jobs import start_scheduler, stop_scheduler

log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    log.info("app_starting", env=settings.env, database_configured=settings.database_configured)
    warn_if_auth_disabled()
    if settings.database_configured:
        # Recover runs stranded by a previous crash/restart before serving.
        from app.agents.orchestrator import sweep_orphaned_runs

        try:
            await sweep_orphaned_runs()
        except Exception as exc:  # noqa: BLE001 - sweep failure must not block boot
            log.error("orphan_sweep_failed", error=str(exc), exc_info=True)
        start_scheduler()
    else:
        log.warning("scheduler_skipped_no_database")
    yield
    stop_scheduler()
    await dispose_engine()
    log.info("app_stopped")


app = FastAPI(
    title="AI Financial Intelligence Platform",
    description=(
        "Market data ingestion, technical indicators, forecasting, NautilusTrader "
        "backtesting, and a multi-agent analysis pipeline for a fixed 16-asset "
        "Indian-market universe. Decision-support only - no real trading."
    ),
    version="0.2.5",
    lifespan=lifespan,
)

# Middleware order: request-id outermost, then rate limiting.
app.add_middleware(RequestIDMiddleware)
app.add_middleware(RateLimitMiddleware)

_cors = [o.strip() for o in get_settings().cors_origins.split(",") if o.strip()]
if _cors:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Protected business routers, mounted at both the legacy root and /api/v1.
# The root mount is kept for backward compatibility; /api/v1 is canonical.
_PROTECTED = [instruments.router, ingest.router, backtest.router, agents.router]
_auth = [Depends(require_api_key)]
for router in _PROTECTED:
    app.include_router(router, dependencies=_auth)
    app.include_router(router, prefix="/api/v1", dependencies=_auth, include_in_schema=False)

# Probes are always open (rate limiter + auth both skip them).
app.include_router(health.router)


@app.get("/live", tags=["health"])
async def live() -> dict:
    """Pure liveness probe - no dependencies touched."""
    return {"status": "alive"}


# Prometheus metrics (behind the API key when configured).
try:
    from prometheus_fastapi_instrumentator import Instrumentator

    Instrumentator(excluded_handlers=["/metrics", "/live", "/health"]).instrument(app).expose(
        app, endpoint="/metrics", dependencies=_auth, include_in_schema=False
    )
except ImportError:  # pragma: no cover - metrics optional at runtime
    log.warning("metrics_unavailable", reason="prometheus_fastapi_instrumentator not installed")


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Last-resort handler: log with stack trace, return a clean 500."""
    log.error(
        "unhandled_exception",
        path=str(request.url.path),
        method=request.method,
        error=str(exc),
        error_type=type(exc).__name__,
        exc_info=True,
    )
    return JSONResponse(status_code=500, content={"detail": "internal server error"})
