"""Data-ingestion trigger endpoint.

Hardening (Phase 2.5, audit MED-4): a process-wide mutex rejects concurrent
ingests (409), and ``background=true`` runs the fetch outside the request
(202-style response with ``status='started'``) to avoid gateway timeouts.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_session, get_sessionmaker
from app.schemas.market import IngestRequest, IngestSummaryOut, InstrumentIngestOut
from app.services import data_ingest

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/ingest", tags=["ingest"])

_ingest_active = False  # loop-confined flag (no await between check and set)


def _summary_out(summary: data_ingest.IngestSummary, status: str = "completed") -> IngestSummaryOut:
    return IngestSummaryOut(
        status=status,
        total_instruments=summary.total_instruments,
        total_inserted=summary.total_inserted,
        total_fetched=summary.total_fetched,
        results=[
            InstrumentIngestOut(
                symbol=r.symbol,
                provider_symbol=r.provider_symbol,
                fetched=r.fetched,
                inserted=r.inserted,
                skipped=r.skipped,
                error=r.error,
            )
            for r in summary.results
        ],
    )


async def _run_ingest_background(body: IngestRequest) -> None:
    global _ingest_active
    try:
        sm = get_sessionmaker()
        async with sm() as session:
            await data_ingest.ingest_all(
                session, symbols=body.symbols, start=body.start, end=body.end, days=body.days
            )
    except Exception as exc:  # noqa: BLE001 - background job records via logs
        log.error("background_ingest_failed", error=str(exc), exc_info=True)
    finally:
        _ingest_active = False


def start_background_ingest(
    background_tasks: BackgroundTasks, *, symbols: list[str] | None, days: int
) -> bool:
    """Queue a background ingest honoring the process-wide mutex.

    Shared with the admin catalog-sync backfill (Phase 6). Returns False when
    an ingest is already running (caller decides whether that's a 409 or a
    soft skip).
    """
    global _ingest_active
    if _ingest_active:
        return False
    _ingest_active = True
    background_tasks.add_task(_run_ingest_background, IngestRequest(symbols=symbols, days=days))
    return True


@router.post("/run", response_model=IngestSummaryOut)
async def run_ingest(
    background_tasks: BackgroundTasks,
    body: IngestRequest | None = None,
    session: AsyncSession = Depends(get_session),
) -> IngestSummaryOut:
    """Fetch and upsert OHLCV for the universe (or a subset). Idempotent."""
    global _ingest_active
    body = body or IngestRequest()
    if _ingest_active:
        raise HTTPException(status_code=409, detail="an ingest is already running")

    if body.background:
        _ingest_active = True
        background_tasks.add_task(_run_ingest_background, body)
        return IngestSummaryOut(
            status="started", total_instruments=0, total_inserted=0, total_fetched=0, results=[]
        )

    _ingest_active = True
    try:
        summary = await data_ingest.ingest_all(
            session, symbols=body.symbols, start=body.start, end=body.end, days=body.days
        )
    finally:
        _ingest_active = False
    return _summary_out(summary)
