"""Read-side data access for instruments, providers, and price bars.

These helpers are shared by the API routers, the indicator/forecast services,
and the backtester. They query the pre-existing schema (UUID keys, price_bars).
"""

from __future__ import annotations

import uuid
from datetime import date

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.instruments import DEFAULT_TIMEFRAME, YFINANCE_PROVIDER_CODE
from app.models.instrument import Instrument
from app.models.price_bar import PriceBar
from app.models.provider import DataProvider, InstrumentProviderMapping


async def list_instruments(session: AsyncSession, *, active_only: bool = True) -> list[Instrument]:
    stmt = select(Instrument)
    if active_only:
        stmt = stmt.where(Instrument.status == "active")
    stmt = stmt.order_by(Instrument.symbol)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_instrument_by_symbol(session: AsyncSession, symbol: str) -> Instrument | None:
    result = await session.execute(select(Instrument).where(Instrument.symbol == symbol))
    return result.scalar_one_or_none()


async def get_provider_by_code(session: AsyncSession, code: str) -> DataProvider | None:
    result = await session.execute(select(DataProvider).where(DataProvider.code == code))
    return result.scalar_one_or_none()


async def get_yfinance_provider(session: AsyncSession) -> DataProvider:
    provider = await get_provider_by_code(session, YFINANCE_PROVIDER_CODE)
    if provider is None:
        raise LookupError(
            f"data_providers row with code '{YFINANCE_PROVIDER_CODE}' not found. "
            "The instrument/provider registry must be seeded first."
        )
    return provider


async def get_provider_symbol_map(
    session: AsyncSession, provider_id: uuid.UUID
) -> dict[uuid.UUID, str]:
    """Return {instrument_id: provider_symbol} for a provider's active mappings."""
    stmt = select(
        InstrumentProviderMapping.instrument_id,
        InstrumentProviderMapping.provider_symbol,
    ).where(
        InstrumentProviderMapping.provider_id == provider_id,
        InstrumentProviderMapping.is_active.is_(True),
    )
    result = await session.execute(stmt)
    return {row.instrument_id: row.provider_symbol for row in result}


async def get_provider_symbol(
    session: AsyncSession, instrument_id: uuid.UUID, provider_id: uuid.UUID
) -> str | None:
    stmt = select(InstrumentProviderMapping.provider_symbol).where(
        InstrumentProviderMapping.instrument_id == instrument_id,
        InstrumentProviderMapping.provider_id == provider_id,
        InstrumentProviderMapping.is_active.is_(True),
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_price_bars(
    session: AsyncSession,
    instrument_id: uuid.UUID,
    *,
    start: date | None = None,
    end: date | None = None,
    timeframe: str = DEFAULT_TIMEFRAME,
) -> list[PriceBar]:
    stmt = select(PriceBar).where(
        PriceBar.instrument_id == instrument_id,
        PriceBar.timeframe == timeframe,
    )
    if start is not None:
        stmt = stmt.where(PriceBar.date >= start)
    if end is not None:
        stmt = stmt.where(PriceBar.date <= end)
    stmt = stmt.order_by(PriceBar.date)
    result = await session.execute(stmt)
    return list(result.scalars().all())


SUMMARY_BARS = 30  # sparkline length; also covers the 20d change window


async def universe_summary(
    session: AsyncSession,
    *,
    instrument_ids: list[uuid.UUID] | None = None,
    q: str | None = None,
    types: list[str] | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> dict:
    """Dashboard payload (Phase 6: filterable + paged): latest close, 1/5/20-day
    changes, and a sparkline per instrument. Returns {items, total}.

    The instrument page is resolved FIRST (filters + slice), then one
    window-function query pulls the recent bars for only that page, so cost is
    bounded by the page size - not the whole price_bars table.
    """
    stmt = select(Instrument).where(Instrument.status == "active")
    if instrument_ids is not None:
        stmt = stmt.where(Instrument.id.in_(instrument_ids))
    if q:
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(
            Instrument.symbol.ilike(pattern) | Instrument.display_name.ilike(pattern)
        )
    if types:
        stmt = stmt.where(Instrument.instrument_type.in_(types))
    stmt = stmt.order_by(Instrument.symbol)

    # Instrument rows are tiny and the universe is capped (~300): fetch the
    # filtered set once, slice in Python for the page + total.
    matching = list((await session.execute(stmt)).scalars().all())
    total = len(matching)
    instruments = matching[offset : offset + limit] if limit is not None else matching[offset:]
    if not instruments:
        return {"items": [], "total": total}
    page_ids = [i.id for i in instruments]

    rn = (
        func.row_number()
        .over(partition_by=PriceBar.instrument_id, order_by=PriceBar.date.desc())
        .label("rn")
    )
    recent = (
        select(PriceBar.instrument_id, PriceBar.date, PriceBar.close, PriceBar.adj_close, rn)
        .where(
            PriceBar.timeframe == DEFAULT_TIMEFRAME,
            PriceBar.instrument_id.in_(page_ids),
        )
        .subquery()
    )
    result = await session.execute(
        select(recent).where(recent.c.rn <= SUMMARY_BARS).order_by(recent.c.date)
    )
    by_instrument: dict[uuid.UUID, list] = {}
    for row in result:
        by_instrument.setdefault(row.instrument_id, []).append(row)

    def pct_change(rows: list, days_back: int) -> float | None:
        # rows are ascending by date; adjusted closes for split-safe ratios.
        if len(rows) <= days_back:
            return None
        last = float(rows[-1].adj_close or rows[-1].close)
        base = float(rows[-1 - days_back].adj_close or rows[-1 - days_back].close)
        if base == 0:
            return None
        return round((last / base - 1.0) * 100, 2)

    items = []
    for inst in instruments:
        rows = by_instrument.get(inst.id, [])
        entry: dict = {
            "symbol": inst.symbol,
            "display_name": inst.display_name,
            "instrument_type": inst.instrument_type,
            "last_date": rows[-1].date if rows else None,
            "last_close": round(float(rows[-1].close), 2) if rows else None,
            "change_1d_pct": pct_change(rows, 1),
            "change_5d_pct": pct_change(rows, 5),
            "change_20d_pct": pct_change(rows, 20),
            "sparkline": [round(float(r.adj_close or r.close), 2) for r in rows],
        }
        items.append(entry)
    return {"items": items, "total": total}


async def price_bars_dataframe(
    session: AsyncSession,
    instrument_id: uuid.UUID,
    *,
    start: date | None = None,
    end: date | None = None,
    timeframe: str = DEFAULT_TIMEFRAME,
) -> pd.DataFrame:
    """Return price bars as a DataFrame indexed by date with float OHLCV columns.

    Columns: open, high, low, close, adj_close, volume. Empty frame (with those
    columns) if there are no bars.
    """
    bars = await get_price_bars(
        session, instrument_id, start=start, end=end, timeframe=timeframe
    )
    cols = ["open", "high", "low", "close", "adj_close", "volume"]
    if not bars:
        empty = pd.DataFrame(columns=cols)
        empty.index = pd.DatetimeIndex([], name="date")
        return empty
    data = {
        "date": [b.date for b in bars],
        "open": [float(b.open) for b in bars],
        "high": [float(b.high) for b in bars],
        "low": [float(b.low) for b in bars],
        "close": [float(b.close) for b in bars],
        "adj_close": [
            float(b.adj_close) if b.adj_close is not None else float(b.close) for b in bars
        ],
        "volume": [int(b.volume) for b in bars],
    }
    df = pd.DataFrame(data)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    return df
