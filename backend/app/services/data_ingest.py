"""Market-data ingestion: fetch OHLCV from yfinance and upsert into price_bars.

Design notes:
* ``auto_adjust=False`` so raw close and adj_close are both preserved (a known
  pitfall from the project handover).
* Upserts are idempotent via ON CONFLICT DO NOTHING on the natural key
  (instrument_id, provider_id, date, timeframe) - re-running never errors.
* The blocking yfinance call is run in a thread so it does not block the loop.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd
import structlog
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.instruments import DEFAULT_CURRENCY, DEFAULT_TIMEFRAME
from app.models.price_bar import PriceBar
from app.services import market_data

log = structlog.get_logger(__name__)

_OHLC_FIELDS = ("Open", "High", "Low", "Close")


@dataclass
class InstrumentIngestResult:
    symbol: str
    provider_symbol: str
    fetched: int = 0
    inserted: int = 0
    skipped: int = 0
    error: str | None = None


@dataclass
class IngestSummary:
    total_instruments: int = 0
    total_inserted: int = 0
    total_fetched: int = 0
    results: list[InstrumentIngestResult] = field(default_factory=list)


def fetch_ohlcv_df(yf_symbol: str, start: date, end: date) -> pd.DataFrame:
    """Fetch daily OHLCV from yfinance. Returns an empty frame on no data.

    ``end`` is inclusive here (yfinance treats end as exclusive, so we add a day).
    """
    import yfinance as yf

    raw = yf.download(
        yf_symbol,
        start=start.isoformat(),
        end=(end + timedelta(days=1)).isoformat(),
        auto_adjust=False,
        actions=False,
        progress=False,
        threads=False,
    )
    if raw is None or raw.empty:
        return pd.DataFrame()
    # Single-ticker downloads may still come back with MultiIndex columns.
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    return raw


def normalize_bars(
    df: pd.DataFrame,
    instrument_id: uuid.UUID,
    provider_id: uuid.UUID,
    *,
    currency: str = DEFAULT_CURRENCY,
    timeframe: str = DEFAULT_TIMEFRAME,
) -> list[dict]:
    """Convert a yfinance OHLCV frame into price_bars row dicts (pure function).

    Rows with missing OHLC values are dropped. ``id`` is generated here because
    price_bars has no DB-side UUID default.
    """
    rows: list[dict] = []
    for idx, row in df.iterrows():
        bar_date = idx.date() if hasattr(idx, "date") else idx
        values = {f: row.get(f) for f in _OHLC_FIELDS}
        if any(v is None or pd.isna(v) for v in values.values()):
            continue
        adj = row.get("Adj Close")
        vol = row.get("Volume")
        rows.append(
            {
                "id": uuid.uuid4(),
                "instrument_id": instrument_id,
                "provider_id": provider_id,
                "date": bar_date,
                "timeframe": timeframe,
                "open": float(values["Open"]),
                "high": float(values["High"]),
                "low": float(values["Low"]),
                "close": float(values["Close"]),
                "adj_close": None if adj is None or pd.isna(adj) else float(adj),
                "volume": 0 if vol is None or pd.isna(vol) else int(vol),
                "currency": currency,
                "is_adjusted": False,
                "provider_version": "yfinance",
            }
        )
    return rows


async def upsert_price_bars(session: AsyncSession, rows: list[dict]) -> int:
    """Insert bars, skipping any that already exist. Returns the number inserted."""
    if not rows:
        return 0
    stmt = pg_insert(PriceBar).values(rows).on_conflict_do_nothing(
        index_elements=["instrument_id", "provider_id", "date", "timeframe"]
    )
    result = await session.execute(stmt)
    await session.commit()
    # rowcount reflects the number actually inserted (conflicts excluded).
    rowcount: int | None = getattr(result, "rowcount", None)
    return rowcount if rowcount is not None and rowcount >= 0 else 0


async def _fetch_with_retry(
    yf_symbol: str, start: date, end: date, *, attempts: int = 3
) -> pd.DataFrame:
    delay = 1.0
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return await asyncio.to_thread(fetch_ohlcv_df, yf_symbol, start, end)
        except Exception as exc:  # noqa: BLE001 - retry any transient fetch error
            last_exc = exc
            log.warning(
                "ohlcv_fetch_retry", symbol=yf_symbol, attempt=attempt, error=str(exc)
            )
            if attempt < attempts:
                await asyncio.sleep(delay)
                delay *= 2
    assert last_exc is not None
    raise last_exc


async def ingest_instrument(
    session: AsyncSession,
    instrument_id: uuid.UUID,
    symbol: str,
    currency: str,
    provider_id: uuid.UUID,
    yf_symbol: str,
    start: date,
    end: date,
) -> InstrumentIngestResult:
    """Ingest one instrument. Takes PLAIN values, never ORM objects: a rollback
    in the error path expires ORM instances, and touching an expired attribute
    afterwards raises MissingGreenlet (found by the DB integration suite)."""
    res = InstrumentIngestResult(symbol=symbol, provider_symbol=yf_symbol)
    try:
        df = await _fetch_with_retry(yf_symbol, start, end)
        rows = normalize_bars(
            df, instrument_id, provider_id, currency=currency or DEFAULT_CURRENCY
        )
        res.fetched = len(rows)
        res.inserted = await upsert_price_bars(session, rows)
        res.skipped = res.fetched - res.inserted
        log.info(
            "ingest_instrument_ok",
            symbol=symbol,
            yf_symbol=yf_symbol,
            fetched=res.fetched,
            inserted=res.inserted,
        )
    except Exception as exc:  # noqa: BLE001 - record and continue with others
        # A failed DB statement leaves the shared session in an aborted
        # transaction; without rollback every later instrument would fail with
        # PendingRollbackError (audit HIGH-2).
        await session.rollback()
        res.error = str(exc)
        log.error("ingest_instrument_failed", symbol=symbol, error=str(exc))
    return res


async def ingest_all(
    session: AsyncSession,
    *,
    symbols: list[str] | None = None,
    start: date | None = None,
    end: date | None = None,
    days: int | None = None,
) -> IngestSummary:
    """Ingest OHLCV for the given symbols (or the whole active universe).

    Date range: explicit start/end, else the last ``days`` days, else the last
    365 days.
    """
    end = end or date.today()
    if start is None:
        lookback = days if days is not None else 365
        start = end - timedelta(days=lookback)

    provider = await market_data.get_yfinance_provider(session)
    provider_id = provider.id
    symbol_map = await market_data.get_provider_symbol_map(session, provider_id)
    instruments = await market_data.list_instruments(session, active_only=True)
    if symbols:
        wanted = {s.upper() for s in symbols}
        instruments = [i for i in instruments if i.symbol.upper() in wanted]

    # Snapshot plain values up front: after any mid-loop rollback the ORM
    # objects are expired and must not be touched again.
    targets = [(i.id, i.symbol, i.currency) for i in instruments]

    summary = IngestSummary(total_instruments=len(targets))
    for instrument_id, symbol, currency in targets:
        yf_symbol = symbol_map.get(instrument_id)
        if not yf_symbol:
            res = InstrumentIngestResult(
                symbol=symbol,
                provider_symbol="",
                error="no active yfinance provider mapping",
            )
            summary.results.append(res)
            continue
        res = await ingest_instrument(
            session, instrument_id, symbol, currency, provider_id, yf_symbol, start, end
        )
        summary.results.append(res)
        summary.total_inserted += res.inserted
        summary.total_fetched += res.fetched
        # Gentleness knob (Phase 6): at ~100 instruments a sequential burst can
        # trip yfinance throttling; a short pause between symbols avoids it.
        pause = get_settings().ingest_pause_seconds
        if pause > 0:
            await asyncio.sleep(pause)

    log.info(
        "ingest_all_done",
        instruments=summary.total_instruments,
        inserted=summary.total_inserted,
        fetched=summary.total_fetched,
    )
    return summary
