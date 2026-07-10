"""Forecast orchestration: load history, run a forecaster, persist predictions."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import date

import pandas as pd
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.ml.base import ForecasterError, ForecastResult
from app.ml.registry import get_forecaster
from app.models.forecast import Forecast
from app.models.instrument import Instrument
from app.services import market_data

log = structlog.get_logger(__name__)


@dataclass
class ForecastRun:
    instrument: Instrument
    result: ForecastResult
    target_dates: list[date]


async def run_forecast(
    session: AsyncSession,
    symbol: str,
    horizon: int,
    *,
    model_name: str | None = None,
    persist: bool = True,
    user_id: uuid.UUID | None = None,
) -> ForecastRun:
    instrument = await market_data.get_instrument_by_symbol(session, symbol)
    if instrument is None:
        raise LookupError(f"instrument '{symbol}' not found")

    df = await market_data.price_bars_dataframe(session, instrument.id)
    if df.empty:
        raise ForecasterError(f"no price history for '{symbol}'; ingest data first")

    forecaster = get_forecaster(model_name)
    # Model load/inference is CPU-bound; keep it off the event loop (CRIT-2).
    result = await asyncio.to_thread(forecaster.forecast, df, horizon)

    last_date = pd.to_datetime(df.index[-1])
    target_dates = [
        d.date()
        for d in pd.bdate_range(start=last_date + pd.offsets.BDay(1), periods=horizon)
    ]

    if persist:
        session.add_all(
            [
                Forecast(
                    instrument_id=instrument.id,
                    user_id=user_id,
                    model_name=result.model_name,
                    horizon=horizon,
                    step=i + 1,
                    target_date=target_dates[i],
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
        )

    return ForecastRun(instrument=instrument, result=result, target_dates=target_dates)
