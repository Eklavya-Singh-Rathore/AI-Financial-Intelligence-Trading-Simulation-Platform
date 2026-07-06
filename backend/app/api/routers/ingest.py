"""Data-ingestion trigger endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_session
from app.schemas.market import IngestRequest, IngestSummaryOut, InstrumentIngestOut
from app.services import data_ingest

router = APIRouter(prefix="/ingest", tags=["ingest"])


@router.post("/run", response_model=IngestSummaryOut)
async def run_ingest(
    body: IngestRequest | None = None,
    session: AsyncSession = Depends(get_session),
) -> IngestSummaryOut:
    """Fetch and upsert OHLCV for the universe (or a subset). Idempotent."""
    body = body or IngestRequest()
    summary = await data_ingest.ingest_all(
        session,
        symbols=body.symbols,
        start=body.start,
        end=body.end,
        days=body.days,
    )
    return IngestSummaryOut(
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
