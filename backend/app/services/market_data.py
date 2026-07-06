"""Read-side data access for instruments, providers, and price bars.

These helpers are shared by the API routers, the indicator/forecast services,
and the backtester. They query the pre-existing schema (UUID keys, price_bars).
"""

from __future__ import annotations

import uuid
from datetime import date

import pandas as pd
from sqlalchemy import select
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
