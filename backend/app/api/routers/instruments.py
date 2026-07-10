"""Instrument, price, indicator, and forecast endpoints."""

from __future__ import annotations

from datetime import date
from typing import Annotated

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthContext, get_auth
from app.db.base import get_session
from app.ml.base import ForecasterError
from app.schemas.forecast import ForecastOut, ForecastPoint
from app.schemas.market import (
    IndicatorPoint,
    IndicatorSeriesOut,
    InstrumentOut,
    InstrumentSummaryOut,
    PriceBarOut,
    PriceSeriesOut,
)
from app.services import forecast_service, market_data
from app.services.indicators import SUPPORTED_INDICATORS, compute_indicators

router = APIRouter(prefix="/instruments", tags=["instruments"])


@router.get("", response_model=list[InstrumentOut])
async def list_instruments(
    session: AsyncSession = Depends(get_session),
) -> list[InstrumentOut]:
    instruments = await market_data.list_instruments(session)
    return [InstrumentOut.model_validate(i) for i in instruments]


@router.get("/summary", response_model=list[InstrumentSummaryOut])
async def universe_summary(
    session: AsyncSession = Depends(get_session),
) -> list[InstrumentSummaryOut]:
    """Whole-universe dashboard payload in one call."""
    rows = await market_data.universe_summary(session)
    return [InstrumentSummaryOut.model_validate(r) for r in rows]


async def _get_instrument_or_404(session: AsyncSession, symbol: str):
    instrument = await market_data.get_instrument_by_symbol(session, symbol.upper())
    if instrument is None:
        raise HTTPException(status_code=404, detail=f"instrument '{symbol}' not found")
    return instrument


@router.get("/{symbol}/prices", response_model=PriceSeriesOut)
async def get_prices(
    symbol: str,
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    limit: int = Query(
        default=10_000,
        ge=1,
        le=50_000,
        description="Maximum bars returned (most recent kept).",
    ),
    session: AsyncSession = Depends(get_session),
) -> PriceSeriesOut:
    instrument = await _get_instrument_or_404(session, symbol)
    bars = await market_data.get_price_bars(session, instrument.id, start=start, end=end)
    if len(bars) > limit:
        bars = bars[-limit:]
    out = [
        PriceBarOut(
            date=b.date,
            open=float(b.open),
            high=float(b.high),
            low=float(b.low),
            close=float(b.close),
            adj_close=float(b.adj_close) if b.adj_close is not None else None,
            volume=int(b.volume),
        )
        for b in bars
    ]
    return PriceSeriesOut(symbol=instrument.symbol, count=len(out), bars=out)


@router.get("/{symbol}/indicators", response_model=IndicatorSeriesOut)
async def get_indicators(
    symbol: str,
    names: str = Query(
        default="sma,rsi",
        description=f"Comma-separated indicators: {', '.join(SUPPORTED_INDICATORS)}",
    ),
    start: date | None = Query(default=None),
    end: date | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> IndicatorSeriesOut:
    requested = [n.strip().lower() for n in names.split(",") if n.strip()]
    unknown = [n for n in requested if n not in SUPPORTED_INDICATORS]
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"unknown indicators: {unknown}. Supported: {list(SUPPORTED_INDICATORS)}",
        )
    instrument = await _get_instrument_or_404(session, symbol)
    df = await market_data.price_bars_dataframe(session, instrument.id, start=start, end=end)
    if df.empty:
        return IndicatorSeriesOut(
            symbol=instrument.symbol, indicators=requested, count=0, points=[]
        )
    values = compute_indicators(df, requested)
    records = values.where(pd.notna(values), None).to_dict(orient="index")
    points = [
        IndicatorPoint(
            date=idx.date(),
            values={k: (None if v is None else float(v)) for k, v in records[idx].items()},
        )
        for idx in values.index
    ]
    return IndicatorSeriesOut(
        symbol=instrument.symbol,
        indicators=requested,
        count=len(points),
        points=points,
    )


@router.get("/{symbol}/forecast", response_model=ForecastOut)
async def get_forecast(
    symbol: str,
    auth: Annotated[AuthContext, Depends(get_auth)],
    horizon: int = Query(default=5, ge=1, le=60),
    model: str | None = Query(default=None, description="'kronos' or 'baseline'"),
    persist: bool = Query(default=True),
    session: AsyncSession = Depends(get_session),
) -> ForecastOut:
    try:
        run = await forecast_service.run_forecast(
            session,
            symbol.upper(),
            horizon,
            model_name=model,
            persist=persist,
            user_id=auth.user_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ForecasterError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    points = [
        ForecastPoint(
            step=i + 1,
            target_date=run.target_dates[i],
            predicted_close=run.result.predictions[i],
        )
        for i in range(len(run.result.predictions))
    ]
    return ForecastOut(
        symbol=run.instrument.symbol,
        model_name=run.result.model_name,
        horizon=run.result.horizon,
        points=points,
        meta=run.result.meta,
    )
