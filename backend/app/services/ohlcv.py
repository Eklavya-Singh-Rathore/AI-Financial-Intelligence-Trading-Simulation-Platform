"""Multi-interval OHLCV resolver (Phase 6.5).

One entry point — ``get_bars`` / ``get_bars_df`` — that returns bars at any
supported interval:

* ``1D``           → stored ``price_bars`` (daily).
* ``1W`` / ``1M``  → stored daily, resampled.
* ``1m``…``1H``    → yfinance intraday, fetched on demand (NOT persisted) and
  cached in-process for a short TTL so repeated loads (prices + indicators
  queries fire separately) don't hammer Yahoo.

Intraday timestamps are emitted as naive exchange-local wall-clock ISO strings
(e.g. ``2026-07-20T09:15:00``) so the chart renders IST session times directly.
Daily/weekly/monthly emit plain ISO dates (``2026-07-17``).
"""

from __future__ import annotations

import asyncio
import time
from datetime import time as _time_of_day
from typing import Literal, TypedDict

import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession

from app.providers.base import OhlcvBar
from app.services import data_ingest, market_data


class _IntervalCfg(TypedDict, total=False):
    kind: Literal["daily", "resample", "intraday"]
    yf: str  # yfinance interval (intraday)
    period: str  # yfinance look-back window (intraday)
    rule: str  # pandas resample rule (resample)


# Yahoo intraday history limits bound the periods: 1m ≤ 7d, 5m/15m/30m ≤ 60d,
# 60m ≤ 730d. Keys are the API/UI interval names.
INTERVALS: dict[str, _IntervalCfg] = {
    "1m": {"kind": "intraday", "yf": "1m", "period": "7d"},
    "5m": {"kind": "intraday", "yf": "5m", "period": "60d"},
    "15m": {"kind": "intraday", "yf": "15m", "period": "60d"},
    "30m": {"kind": "intraday", "yf": "30m", "period": "60d"},
    "1H": {"kind": "intraday", "yf": "60m", "period": "730d"},
    "1D": {"kind": "daily"},
    "1W": {"kind": "resample", "rule": "W-FRI"},
    "1M": {"kind": "resample", "rule": "ME"},
}
VALID_INTERVALS: tuple[str, ...] = tuple(INTERVALS)
DEFAULT_INTERVAL = "1D"

_INTRADAY_TTL_SECONDS = 60.0
_intraday_cache: dict[tuple[str, str], tuple[float, pd.DataFrame]] = {}


def is_intraday(interval: str) -> bool:
    return INTERVALS.get(interval, {}).get("kind") == "intraday"


def time_str(idx: pd.Timestamp, intraday: bool) -> str:
    """Format a DataFrame index label as the wire ISO time for a bar."""
    if intraday:
        ts = idx.tz_localize(None) if idx.tzinfo is not None else idx
        return ts.strftime("%Y-%m-%dT%H:%M:%S")
    return idx.strftime("%Y-%m-%d")


# NSE regular session (IST). Exchange holidays are not modelled - matching the
# daily business-day path, which also only skips weekends.
_SESSION_OPEN = _time_of_day(9, 15)
_SESSION_CLOSE = _time_of_day(15, 30)
_OPEN_OFFSET = pd.Timedelta(hours=9, minutes=15)
_INTRADAY_STEP_MINUTES = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1H": 60}


def _next_session_open(ts: pd.Timestamp) -> pd.Timestamp:
    """The 09:15 open of the next weekday session after ``ts``."""
    nxt = (ts + pd.Timedelta(days=1)).normalize() + _OPEN_OFFSET
    while nxt.weekday() >= 5:
        nxt = (nxt + pd.Timedelta(days=1)).normalize() + _OPEN_OFFSET
    return nxt


def future_timestamps(last_ts: pd.Timestamp, interval: str, periods: int) -> pd.DatetimeIndex:
    """Future bar timestamps at the interval's cadence, starting after ``last_ts``.

    Daily -> business days; weekly/monthly -> the resample offset; intraday ->
    session-aware steps within NSE hours (09:15-15:30 IST, weekends skipped).
    Returned naive (tz-dropped) so intraday labels match the wire wall-clock.
    """
    if periods < 1:
        return pd.DatetimeIndex([])
    cfg = INTERVALS.get(interval, {"kind": "daily"})
    kind = cfg.get("kind", "daily")
    last = pd.Timestamp(last_ts)
    if last.tzinfo is not None:
        last = last.tz_localize(None)

    if kind == "daily":
        return pd.bdate_range(start=last + pd.offsets.BDay(1), periods=periods)
    if kind == "resample":
        # Anchored freq (W-FRI / ME) from `last`; drop the anchor if `last` is on
        # it, then take the next `periods`. +2 buffers the possible dropped anchor.
        idx = pd.date_range(start=last, periods=periods + 2, freq=cfg["rule"])
        return pd.DatetimeIndex(idx[idx > last][:periods])

    # intraday
    step = pd.Timedelta(minutes=_INTRADAY_STEP_MINUTES.get(interval, 5))
    bars: list[pd.Timestamp] = []
    cur = last
    while len(bars) < periods:
        cur = cur + step
        if cur.weekday() >= 5 or cur.time() >= _SESSION_CLOSE:
            cur = _next_session_open(cur)
        elif cur.time() < _SESSION_OPEN:
            cur = cur.normalize() + _OPEN_OFFSET
        bars.append(cur)
    return pd.DatetimeIndex(bars)


_RESAMPLE_AGG = {
    "open": "first",
    "high": "max",
    "low": "min",
    "close": "last",
    "adj_close": "last",
    "volume": "sum",
}


def _resample(daily: pd.DataFrame, rule: str) -> pd.DataFrame:
    if daily.empty:
        return daily
    out = daily.resample(rule).agg(_RESAMPLE_AGG)
    return out.dropna(subset=["close"])


def _normalize_intraday(raw: pd.DataFrame) -> pd.DataFrame:
    """yfinance intraday frame → lowercase OHLCV columns, datetime index."""
    if raw.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close", "adj_close", "volume"])
    rename = {
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Adj Close": "adj_close",
        "Volume": "volume",
    }
    df = raw.rename(columns=rename)
    keep = [c for c in ["open", "high", "low", "close", "adj_close", "volume"] if c in df.columns]
    df = df[keep].dropna(subset=["close"])
    df.index = pd.DatetimeIndex(df.index)
    return df


async def _yf_symbol(session: AsyncSession, instrument_id) -> str:
    provider = await market_data.get_yfinance_provider(session)
    mapping = await market_data.get_provider_symbol_map(session, provider.id)
    yf_symbol = mapping.get(instrument_id)
    if not yf_symbol:
        raise LookupError("no yfinance provider mapping for instrument")
    return yf_symbol


async def _resolve_df(session: AsyncSession, symbol: str, interval: str) -> pd.DataFrame:
    if interval not in INTERVALS:
        raise ValueError(f"unsupported interval '{interval}'")
    cfg = INTERVALS[interval]
    instrument = await market_data.get_instrument_by_symbol(session, symbol.upper())
    if instrument is None:
        raise LookupError(f"instrument '{symbol}' not found")

    if cfg["kind"] == "daily":
        return await market_data.price_bars_dataframe(session, instrument.id)
    if cfg["kind"] == "resample":
        daily = await market_data.price_bars_dataframe(session, instrument.id)
        return _resample(daily, cfg["rule"])

    # intraday — cached on-demand yfinance fetch
    key = (symbol.upper(), interval)
    now = time.monotonic()
    hit = _intraday_cache.get(key)
    if hit is not None and hit[0] > now:
        return hit[1]
    yf_symbol = await _yf_symbol(session, instrument.id)
    raw = await asyncio.to_thread(
        data_ingest.fetch_intraday_df, yf_symbol, cfg["yf"], cfg["period"]
    )
    df = _normalize_intraday(raw)
    _intraday_cache[key] = (now + _INTRADAY_TTL_SECONDS, df)
    return df


async def get_bars_df(session: AsyncSession, symbol: str, interval: str) -> pd.DataFrame:
    """OHLCV DataFrame at the interval (for indicator computation)."""
    return await _resolve_df(session, symbol, interval)


async def get_bars(
    session: AsyncSession, symbol: str, interval: str, *, limit: int | None = None
) -> list[OhlcvBar]:
    """OHLCV bars at the interval, oldest→newest, capped to the last ``limit``."""
    df = await _resolve_df(session, symbol, interval)
    if limit is not None and len(df) > limit:
        df = df.iloc[-limit:]
    intraday = is_intraday(interval)
    bars: list[OhlcvBar] = []
    for idx, row in df.iterrows():
        if pd.isna(row.get("close")):
            continue
        vol = row.get("volume")
        bars.append(
            OhlcvBar(
                time=time_str(idx, intraday),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=int(vol) if vol is not None and not pd.isna(vol) else 0,
            )
        )
    return bars
