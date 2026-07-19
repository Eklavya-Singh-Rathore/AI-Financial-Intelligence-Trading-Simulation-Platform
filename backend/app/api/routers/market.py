"""Whole-market search + track endpoints (Phase 6)."""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthContext, get_auth
from app.db.base import get_session, get_sessionmaker
from app.services import market_expansion
from app.services.market_expansion import TrackError

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/market", tags=["market"])

Auth = Annotated[AuthContext, Depends(get_auth)]


async def _drain_once() -> None:
    """Opportunistic drain kick after a track (advisory-locked; safe to double-fire)."""
    try:
        sm = get_sessionmaker()
        async with sm() as session:
            await market_expansion.drain_ingest_jobs(session)
    except Exception as exc:  # noqa: BLE001 - background best-effort
        log.warning("market_drain_kick_failed", error=str(exc)[:200])


@router.get("/search")
async def search(
    auth: Auth,
    q: str = Query(min_length=2, max_length=48),
    session: AsyncSession = Depends(get_session),
) -> dict:
    return {"results": await market_expansion.search(session, q)}


@router.post("/track")
async def track(
    body: dict,
    background: BackgroundTasks,
    auth: Auth,
    session: AsyncSession = Depends(get_session),
) -> dict:
    symbol = (body.get("symbol") or "").strip()
    if not symbol:
        raise HTTPException(status_code=422, detail="symbol is required")
    try:
        result = await market_expansion.track_symbol(session, symbol, requested_by=auth.user_id)
    except TrackError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if result.job_queued:
        background.add_task(_drain_once)
    return {
        "symbol": result.symbol,
        "provider_symbol": result.provider_symbol,
        "created": result.created,
        "job_queued": result.job_queued,
    }


@router.get("/track/{symbol}/status")
async def track_status(
    symbol: str, auth: Auth, session: AsyncSession = Depends(get_session)
) -> dict:
    try:
        return await market_expansion.track_status(session, symbol)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
