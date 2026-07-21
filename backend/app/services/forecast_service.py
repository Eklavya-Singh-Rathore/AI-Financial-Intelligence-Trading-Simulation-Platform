"""Forecast orchestration: load history, run a forecaster, persist predictions."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime

import pandas as pd
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.ml.base import ForecasterError, ForecastResult
from app.ml.registry import get_forecaster
from app.models.forecast import Forecast
from app.models.instrument import Instrument
from app.services import market_data, ohlcv

log = structlog.get_logger(__name__)


@dataclass
class ForecastRun:
    instrument: Instrument
    result: ForecastResult
    target_dates: list[date]
    interval: str = ohlcv.DEFAULT_INTERVAL
    intraday: bool = False
    target_ts: list[datetime] = field(default_factory=list)


async def run_forecast(
    session: AsyncSession,
    symbol: str,
    horizon: int,
    *,
    interval: str = ohlcv.DEFAULT_INTERVAL,
    model_name: str | None = None,
    persist: bool = True,
    user_id: uuid.UUID | None = None,
) -> ForecastRun:
    interval = interval or ohlcv.DEFAULT_INTERVAL
    if interval not in ohlcv.VALID_INTERVALS:
        raise ValueError(f"unsupported interval '{interval}'")

    instrument = await market_data.get_instrument_by_symbol(session, symbol)
    if instrument is None:
        raise LookupError(f"instrument '{symbol}' not found")

    intraday = ohlcv.is_intraday(interval)
    df = await ohlcv.get_bars_df(session, symbol, interval)
    if df.empty:
        raise ForecasterError(
            f"no price history for '{symbol}' at interval '{interval}'; ingest data first"
        )
    # Intraday frames carry a tz-aware IST index; drop tz to naive wall-clock so
    # model inputs and persisted target timestamps match the chart's wire format.
    if intraday and getattr(df.index, "tz", None) is not None:
        df = df.copy()
        df.index = df.index.tz_localize(None)

    forecaster = get_forecaster(model_name)
    last = pd.to_datetime(df.index[-1])
    target_ts = ohlcv.future_timestamps(last, interval, horizon)

    # Model load/inference is CPU-bound; keep it off the event loop (CRIT-2).
    result = await asyncio.to_thread(
        forecaster.forecast, df, horizon, target_timestamps=pd.Series(target_ts)
    )

    target_dates = [ts.date() for ts in target_ts]
    target_ts_list = [ts.to_pydatetime() for ts in target_ts]

    if persist:
        session.add_all(
            [
                Forecast(
                    instrument_id=instrument.id,
                    user_id=user_id,
                    model_name=result.model_name,
                    horizon=horizon,
                    interval=interval,
                    step=i + 1,
                    target_date=target_dates[i],
                    target_ts=target_ts_list[i] if intraday else None,
                    predicted_close=result.predictions[i],
                    meta=result.meta,
                )
                for i in range(len(result.predictions))
            ]
        )
        await session.commit()
        log.info(
            "forecast_persisted",
            symbol=symbol,
            model=result.model_name,
            horizon=horizon,
            interval=interval,
        )

    return ForecastRun(
        instrument=instrument,
        result=result,
        target_dates=target_dates,
        interval=interval,
        intraday=intraday,
        target_ts=target_ts_list,
    )
