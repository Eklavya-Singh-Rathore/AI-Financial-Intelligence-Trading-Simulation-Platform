"""Whole-market track + drain database-integration tests (Phase 6).

yfinance is monkeypatched (no network); rows under TESTTRK% are cleaned up.
"""

from __future__ import annotations

import uuid

import pandas as pd
import pytest
import pytest_asyncio
from app.core.config import get_settings
from app.db.base import dispose_engine, get_sessionmaker
from app.models.ingest_job import IngestJob
from app.models.instrument import Instrument
from app.models.provider import InstrumentProviderMapping
from app.services import data_ingest, market_expansion
from app.services.market_expansion import TrackError
from sqlalchemy import delete, select, text

pytestmark = [
    pytest.mark.db,
    pytest.mark.skipif(
        not get_settings().database_configured,
        reason="DATABASE_URL not configured; integration tests run in CI",
    ),
]

PROVIDER_ID = uuid.UUID("00000000-0000-4000-8000-000000000003")


@pytest_asyncio.fixture(autouse=True)
async def _fresh_engine():
    import contextlib

    with contextlib.suppress(Exception):
        await dispose_engine()
    yield
    with contextlib.suppress(Exception):
        await dispose_engine()


@pytest_asyncio.fixture()
async def session():
    sm = get_sessionmaker()
    async with sm() as s:
        # Ensure the yfinance provider row exists (track/drain resolve it).
        await s.execute(
            text(
                "INSERT INTO data_providers (id, code, name) "
                "VALUES (:id, 'yfinance', 'Yahoo Finance') ON CONFLICT (code) DO NOTHING"
            ),
            {"id": str(PROVIDER_ID)},
        )
        await s.commit()
        yield s
        ids = (
            (await s.execute(select(Instrument.id).where(Instrument.symbol.like("TESTTRK%"))))
            .scalars()
            .all()
        )
        if ids:
            from app.models.price_bar import PriceBar

            await s.execute(delete(PriceBar).where(PriceBar.instrument_id.in_(ids)))
            await s.execute(delete(IngestJob).where(IngestJob.instrument_id.in_(ids)))
            await s.execute(
                delete(InstrumentProviderMapping).where(
                    InstrumentProviderMapping.instrument_id.in_(ids)
                )
            )
            await s.execute(delete(Instrument).where(Instrument.id.in_(ids)))
            await s.commit()


@pytest.mark.asyncio
async def test_track_creates_instrument_mapping_and_job(session):
    result = await market_expansion.track_symbol(session, "TESTTRK1.NS", requested_by=None)
    assert result.created is True
    assert result.job_queued is True
    assert result.provider_symbol == "TESTTRK1.NS"

    inst = (
        await session.execute(select(Instrument).where(Instrument.symbol == "TESTTRK1"))
    ).scalar_one()
    assert inst.country == "IN"
    mapping = (
        await session.execute(
            select(InstrumentProviderMapping).where(
                InstrumentProviderMapping.instrument_id == inst.id
            )
        )
    ).scalar_one()
    assert mapping.provider_symbol == "TESTTRK1.NS"
    job = (
        await session.execute(select(IngestJob).where(IngestJob.instrument_id == inst.id))
    ).scalar_one()
    assert job.status == "queued"

    # Re-track: idempotent, no new instrument, no second queued job.
    again = await market_expansion.track_symbol(session, "TESTTRK1.NS", requested_by=None)
    assert again.created is False
    assert again.job_queued is False


@pytest.mark.asyncio
async def test_drain_runs_backfill_with_mocked_fetch(session, monkeypatch):
    await market_expansion.track_symbol(session, "TESTTRK2.NS", requested_by=None)

    # Fake yfinance: 3 business days of bars.
    idx = pd.to_datetime(["2026-07-15", "2026-07-16", "2026-07-17"])
    df = pd.DataFrame(
        {"Open": [10, 11, 12], "High": [11, 12, 13], "Low": [9, 10, 11],
         "Close": [10.5, 11.5, 12.5], "Adj Close": [10.5, 11.5, 12.5],
         "Volume": [100, 110, 120]},
        index=idx,
    )
    monkeypatch.setattr(data_ingest, "fetch_ohlcv_df", lambda *a, **k: df)

    ran = await market_expansion.drain_ingest_jobs(session)
    assert ran >= 1

    status = await market_expansion.track_status(session, "TESTTRK2")
    assert status["status"] == "done"
    assert status["bars"] == 3


@pytest.mark.asyncio
async def test_track_cap_returns_409(session, monkeypatch):
    monkeypatch.setattr(get_settings(), "max_tracked_instruments", 0)
    try:
        with pytest.raises(TrackError):
            await market_expansion.track_symbol(session, "TESTTRK3.NS", requested_by=None)
    finally:
        get_settings.cache_clear()
