"""FastAPI application entrypoint.

Run locally with:
    uvicorn app.main:app --reload   (from the backend/ directory)
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.routers import agents, backtest, health, ingest, instruments
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.base import dispose_engine
from app.scheduler.jobs import start_scheduler, stop_scheduler

log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    log.info("app_starting", env=settings.env, database_configured=settings.database_configured)
    if settings.database_configured:
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
        "Phase 1: market data ingestion, technical indicators, Kronos forecasting, "
        "and NautilusTrader backtesting for a fixed 16-asset Indian-market universe. "
        "Decision-support only - no real trading."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(instruments.router)
app.include_router(ingest.router)
app.include_router(backtest.router)
app.include_router(agents.router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Last-resort handler: log with context, return a clean 500."""
    log.error(
        "unhandled_exception",
        path=str(request.url.path),
        method=request.method,
        error=str(exc),
        error_type=type(exc).__name__,
    )
    return JSONResponse(status_code=500, content={"detail": "internal server error"})
