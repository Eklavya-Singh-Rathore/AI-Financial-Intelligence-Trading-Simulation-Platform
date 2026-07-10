"""Backtest orchestration: load history, run an engine, persist the result."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import date

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.backtesting.base import BacktestConfig, BacktesterError, BacktestResult
from app.backtesting.registry import get_backtester
from app.models.backtest import Backtest
from app.models.instrument import Instrument
from app.services import market_data

log = structlog.get_logger(__name__)


@dataclass
class BacktestRun:
    instrument: Instrument
    result: BacktestResult
    start: date | None
    end: date | None


async def run_backtest(
    session: AsyncSession,
    *,
    symbol: str,
    strategy: str = "sma_crossover",
    engine: str = "nautilus",
    start: date | None = None,
    end: date | None = None,
    initial_cash: float = 1_000_000.0,
    params: dict | None = None,
    persist: bool = True,
    user_id: uuid.UUID | None = None,
) -> BacktestRun:
    if strategy != "sma_crossover":
        raise BacktesterError(
            f"unknown strategy '{strategy}'. Available: sma_crossover"
        )

    instrument = await market_data.get_instrument_by_symbol(session, symbol)
    if instrument is None:
        raise LookupError(f"instrument '{symbol}' not found")

    df = await market_data.price_bars_dataframe(session, instrument.id, start=start, end=end)
    if df.empty:
        raise BacktesterError(f"no price history for '{symbol}' in range; ingest data first")

    # Backtest on ADJUSTED prices: raw closes contain corporate-action cliffs
    # (e.g. RELIANCE's 1:1 bonus in Oct 2024 looks like a -50% crash) that
    # corrupt signals and equity marks. Scale OHLC by the per-bar adjustment.
    factor = (df["adj_close"] / df["close"]).fillna(1.0)
    df = df.assign(
        open=df["open"] * factor,
        high=df["high"] * factor,
        low=df["low"] * factor,
        close=df["adj_close"],
    )

    config = BacktestConfig(
        strategy=strategy,
        symbol=symbol,
        params=params or {},
        initial_cash=initial_cash,
        start=start,
        end=end,
    )
    backtester = get_backtester(engine)
    # CPU-bound engine work must not block the event loop (audit CRIT-2).
    result = await asyncio.to_thread(backtester.run, df, config)

    actual_start = df.index[0].date()
    actual_end = df.index[-1].date()

    if persist:
        session.add(
            Backtest(
                user_id=user_id,
                strategy_name=strategy,
                engine=result.engine,
                symbols=[symbol],
                params=config.params | {"initial_cash": initial_cash},
                start_date=actual_start,
                end_date=actual_end,
                metrics=result.metrics,
            )
        )
        await session.commit()
        log.info(
            "backtest_persisted",
            symbol=symbol,
            strategy=strategy,
            engine=result.engine,
            metrics=result.metrics,
        )

    return BacktestRun(
        instrument=instrument, result=result, start=actual_start, end=actual_end
    )
