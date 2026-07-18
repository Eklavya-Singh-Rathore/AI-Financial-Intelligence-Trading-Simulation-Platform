"""Whole-market lazy loading (Phase 6): search, track, background backfill.

A user searches for any Indian symbol, tracks it (creates the instrument +
provider mapping + a queued ``ingest_jobs`` row - NO fetching on the request
path), and a drain worker backfills history. Guardrails: normalize + dedupe,
a hard instrument cap, India-only suffix resolution.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.ingest_job import IngestJob
from app.models.instrument import Instrument
from app.models.price_bar import PriceBar
from app.models.provider import DataProvider, InstrumentProviderMapping
from app.providers import registry as provider_registry
from app.services import data_ingest, market_data

log = structlog.get_logger(__name__)

DRAIN_LOCK_KEY = 815_004

# Yahoo suffix -> exchange code (India only, per the Phase 6 scope decision).
_SUFFIX_EXCHANGE = {".NS": "NSE", ".BO": "BSE"}


class TrackError(ValueError):
    """User-correctable track failure (cap reached, unsupported symbol)."""


@dataclass
class TrackResult:
    symbol: str
    provider_symbol: str
    created: bool
    job_queued: bool


def normalize(provider_symbol: str) -> tuple[str, str, str]:
    """(internal_symbol, provider_symbol, exchange_code) from a Yahoo ticker.

    Indices keep the ``^`` prefix; ``.NS``/``.BO`` map to NSE/BSE; a bare
    symbol defaults to NSE (``.NS`` appended). Raises TrackError for clearly
    non-Indian symbols (no suffix + not an index would default to NSE, which
    is the intended India-only behavior).
    """
    ps = provider_symbol.strip().upper()
    if not ps:
        raise TrackError("empty symbol")
    if ps.startswith("^"):
        return ps.lstrip("^"), ps, "NSE"
    for suffix, exch in _SUFFIX_EXCHANGE.items():
        if ps.endswith(suffix):
            return ps[: -len(suffix)], ps, exch
    # Bare symbol -> assume NSE.
    return ps, f"{ps}.NS", "NSE"


async def search(session: AsyncSession, query: str, *, limit: int = 12) -> list[dict]:
    """Provider symbol search annotated with whether we already track each hit."""
    matches = await _to_thread_search(query, limit)
    if not matches:
        return []
    provider_symbols = {m.provider_symbol.upper() for m in matches}
    tracked = set(
        (
            await session.execute(
                select(InstrumentProviderMapping.provider_symbol).where(
                    func.upper(InstrumentProviderMapping.provider_symbol).in_(provider_symbols)
                )
            )
        ).scalars()
    )
    return [
        {
            "provider_symbol": m.provider_symbol,
            "name": m.name,
            "exchange": m.exchange,
            "asset_type": m.asset_type,
            "already_tracked": m.provider_symbol.upper() in {t.upper() for t in tracked},
        }
        for m in matches
    ]


async def _to_thread_search(query: str, limit: int):
    import asyncio

    return await asyncio.to_thread(provider_registry.search_symbols, query, limit=limit)


async def _get_or_create_exchange(session: AsyncSession, code: str) -> uuid.UUID:
    from app.services.instrument_admin import _get_or_create_exchange as impl

    return await impl(session, code)


async def track_symbol(
    session: AsyncSession, provider_symbol: str, *, requested_by: uuid.UUID | None
) -> TrackResult:
    """Create the instrument + mapping (idempotent) and queue a backfill."""
    internal, psym, exch = normalize(provider_symbol)

    # Dedupe: existing instrument by symbol OR existing provider mapping.
    instrument = await market_data.get_instrument_by_symbol(session, internal)
    if instrument is None:
        instrument = (
            await session.execute(
                select(Instrument)
                .join(
                    InstrumentProviderMapping,
                    InstrumentProviderMapping.instrument_id == Instrument.id,
                )
                .where(func.upper(InstrumentProviderMapping.provider_symbol) == psym.upper())
            )
        ).scalar_one_or_none()

    created = False
    if instrument is None:
        # Cap check only when actually creating a new instrument.
        count = (await session.execute(select(func.count(Instrument.id)))).scalar() or 0
        if count >= get_settings().max_tracked_instruments:
            raise TrackError(
                f"tracked-instrument limit reached ({get_settings().max_tracked_instruments})"
            )
        provider = await _yf_provider(session)
        exchange_id = await _get_or_create_exchange(session, exch)
        now = datetime.now(UTC)
        instrument = Instrument(
            id=uuid.uuid4(),
            symbol=internal,
            display_name=internal,
            instrument_type="index" if psym.startswith("^") else "equity",
            exchange_id=exchange_id,
            currency="INR",
            country="IN",
            status="active",
            created_at=now,
            updated_at=now,
        )
        session.add(instrument)
        await session.flush()
        session.add(
            InstrumentProviderMapping(
                id=uuid.uuid4(),
                instrument_id=instrument.id,
                provider_id=provider.id,
                provider_symbol=psym,
                is_primary=True,
                is_active=True,
                created_at=now,
                updated_at=now,
            )
        )
        created = True

    # Queue a backfill unless a fresh one is already pending/running for it.
    active = (
        await session.execute(
            select(IngestJob.id).where(
                IngestJob.instrument_id == instrument.id,
                IngestJob.status.in_(("queued", "running")),
            )
        )
    ).scalar_one_or_none()
    job_queued = False
    if active is None and (created or not await _has_bars(session, instrument.id)):
        session.add(
            IngestJob(id=uuid.uuid4(), instrument_id=instrument.id, requested_by=requested_by)
        )
        job_queued = True
    await session.commit()
    log.info("symbol_tracked", symbol=internal, created=created, job_queued=job_queued)
    return TrackResult(
        symbol=internal, provider_symbol=psym, created=created, job_queued=job_queued
    )


async def _yf_provider(session: AsyncSession) -> DataProvider:
    try:
        return await market_data.get_yfinance_provider(session)
    except LookupError:
        from app.services.instrument_admin import _get_or_create_provider

        pid = await _get_or_create_provider(session)
        return (
            await session.execute(select(DataProvider).where(DataProvider.id == pid))
        ).scalar_one()


async def _has_bars(session: AsyncSession, instrument_id: uuid.UUID) -> bool:
    return (
        await session.execute(
            select(PriceBar.id).where(PriceBar.instrument_id == instrument_id).limit(1)
        )
    ).scalar_one_or_none() is not None


async def track_status(session: AsyncSession, symbol: str) -> dict:
    """Latest job + bar coverage for a tracked symbol (for the UI to poll)."""
    instrument = await market_data.get_instrument_by_symbol(session, symbol.upper())
    if instrument is None:
        raise LookupError(f"instrument '{symbol}' not found")
    job = (
        await session.execute(
            select(IngestJob)
            .where(IngestJob.instrument_id == instrument.id)
            .order_by(IngestJob.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    bars = (
        await session.execute(
            select(
                func.count(PriceBar.id), func.min(PriceBar.date), func.max(PriceBar.date)
            ).where(PriceBar.instrument_id == instrument.id)
        )
    ).one()
    return {
        "symbol": instrument.symbol,
        "status": job.status if job else ("done" if bars[0] else "none"),
        "bars": int(bars[0] or 0),
        "first_date": bars[1].isoformat() if bars[1] else None,
        "last_date": bars[2].isoformat() if bars[2] else None,
        "error": job.error if job else None,
    }


async def drain_ingest_jobs(session: AsyncSession) -> int:
    """Run queued backfills one at a time (advisory-locked). Returns jobs run.

    Serialized so at most one yfinance backfill runs on the dyno; the queue is
    durable, so a restart mid-drain simply resumes on the next tick.
    """
    from sqlalchemy import text as sa_text

    got_lock = (
        await session.execute(
            sa_text("SELECT pg_try_advisory_lock(:key)"), {"key": DRAIN_LOCK_KEY}
        )
    ).scalar()
    if not got_lock:
        return 0
    ran = 0
    try:
        provider = await market_data.get_yfinance_provider(session)
        while True:
            job = (
                await session.execute(
                    select(IngestJob)
                    .where(IngestJob.status == "queued")
                    .order_by(IngestJob.created_at)
                    .limit(1)
                )
            ).scalar_one_or_none()
            if job is None:
                break
            job.status = "running"
            job.started_at = datetime.now(UTC)
            await session.commit()
            try:
                psym = await market_data.get_provider_symbol(
                    session, job.instrument_id, provider.id
                )
                instrument = (
                    await session.execute(
                        select(Instrument).where(Instrument.id == job.instrument_id)
                    )
                ).scalar_one()
                days = get_settings().default_history_days
                from datetime import date, timedelta

                res = await data_ingest.ingest_instrument(
                    session,
                    job.instrument_id,
                    instrument.symbol,
                    instrument.currency,
                    provider.id,
                    psym or instrument.symbol,
                    date.today() - timedelta(days=days),
                    date.today(),
                )
                job.bars_inserted = res.inserted
                job.error = res.error
                job.status = "error" if res.error and res.inserted == 0 else "done"
            except Exception as exc:  # noqa: BLE001 - one bad job must not stop the drain
                await session.rollback()
                job = (
                    await session.execute(select(IngestJob).where(IngestJob.id == job.id))
                ).scalar_one()
                job.status = "error"
                job.error = str(exc)[:300]
            job.finished_at = datetime.now(UTC)
            await session.commit()
            ran += 1
    finally:
        await session.execute(
            sa_text("SELECT pg_advisory_unlock(:key)"), {"key": DRAIN_LOCK_KEY}
        )
    if ran:
        log.info("ingest_jobs_drained", jobs=ran)
    return ran
