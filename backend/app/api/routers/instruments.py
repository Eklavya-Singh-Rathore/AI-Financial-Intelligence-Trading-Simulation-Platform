"""Instrument, price, indicator, and forecast endpoints."""

from __future__ import annotations

import uuid
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
    UniverseSummaryOut,
)
from app.services import forecast_service, market_data, ohlcv, research, watchlists
from app.services.indicators import SUPPORTED_INDICATORS, compute_indicators

router = APIRouter(prefix="/instruments", tags=["instruments"])


@router.get("", response_model=list[InstrumentOut])
async def list_instruments(
    session: AsyncSession = Depends(get_session),
) -> list[InstrumentOut]:
    instruments = await market_data.list_instruments(session)
    return [InstrumentOut.model_validate(i) for i in instruments]


@router.get("/summary", response_model=UniverseSummaryOut)
async def universe_summary(
    auth: Annotated[AuthContext, Depends(get_auth)],
    q: str | None = Query(default=None, max_length=64, description="Symbol/name search."),
    types: str | None = Query(
        default=None, description="Comma-separated instrument types (equity,index,etf,...)."
    ),
    watchlist_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> UniverseSummaryOut:
    """Filterable, paged dashboard payload (Phase 6)."""
    instrument_ids = None
    if watchlist_id is not None:
        try:
            instrument_ids = await watchlists.watchlist_instrument_ids(
                session, auth.user_id, watchlist_id
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    type_list = [t.strip().lower() for t in types.split(",") if t.strip()] if types else None
    data = await market_data.universe_summary(
        session,
        instrument_ids=instrument_ids,
        q=q,
        types=type_list,
        limit=limit,
        offset=offset,
    )
    return UniverseSummaryOut(
        items=[InstrumentSummaryOut.model_validate(r) for r in data["items"]],
        total=data["total"],
    )


def _validate_interval(interval: str) -> None:
    if interval not in ohlcv.VALID_INTERVALS:
        raise HTTPException(
            status_code=422,
            detail=f"unknown interval '{interval}'. Supported: {list(ohlcv.VALID_INTERVALS)}",
        )


@router.get("/{symbol}/prices", response_model=PriceSeriesOut)
async def get_prices(
    symbol: str,
    interval: str = Query(
        default=ohlcv.DEFAULT_INTERVAL,
        description=f"Bar interval: {', '.join(ohlcv.VALID_INTERVALS)}.",
    ),
    limit: int = Query(
        default=10_000,
        ge=1,
        le=50_000,
        description="Maximum bars returned (most recent kept).",
    ),
    session: AsyncSession = Depends(get_session),
) -> PriceSeriesOut:
    """OHLCV at the requested interval. Daily/weekly/monthly come from stored
    bars; intraday (1m…1H) is fetched on demand from yfinance (Phase 6.5)."""
    _validate_interval(interval)
    try:
        bars = await ohlcv.get_bars(session, symbol, interval, limit=limit)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    out = [
        PriceBarOut(
            date=b.time,
            open=b.open,
            high=b.high,
            low=b.low,
            close=b.close,
            volume=b.volume,
        )
        for b in bars
    ]
    return PriceSeriesOut(symbol=symbol.upper(), count=len(out), bars=out)


@router.get("/{symbol}/indicators", response_model=IndicatorSeriesOut)
async def get_indicators(
    symbol: str,
    names: str = Query(
        default="sma,rsi",
        description=f"Comma-separated indicators: {', '.join(SUPPORTED_INDICATORS)}",
    ),
    interval: str = Query(
        default=ohlcv.DEFAULT_INTERVAL,
        description=f"Bar interval: {', '.join(ohlcv.VALID_INTERVALS)}.",
    ),
    session: AsyncSession = Depends(get_session),
) -> IndicatorSeriesOut:
    requested = [n.strip().lower() for n in names.split(",") if n.strip()]
    unknown = [n for n in requested if n not in SUPPORTED_INDICATORS]
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"unknown indicators: {unknown}. Supported: {list(SUPPORTED_INDICATORS)}",
        )
    _validate_interval(interval)
    try:
        df = await ohlcv.get_bars_df(session, symbol, interval)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if df.empty:
        return IndicatorSeriesOut(
            symbol=symbol.upper(), indicators=requested, count=0, points=[]
        )
    values = compute_indicators(df, requested)
    records = values.where(pd.notna(values), None).to_dict(orient="index")
    intraday = ohlcv.is_intraday(interval)
    points = [
        IndicatorPoint(
            date=ohlcv.time_str(idx, intraday),
            values={k: (None if v is None else float(v)) for k, v in records[idx].items()},
        )
        for idx in values.index
    ]
    return IndicatorSeriesOut(
        symbol=symbol.upper(),
        indicators=requested,
        count=len(points),
        points=points,
    )


@router.get("/{symbol}/forecast", response_model=ForecastOut)
async def get_forecast(
    symbol: str,
    auth: Annotated[AuthContext, Depends(get_auth)],
    horizon: int = Query(default=5, ge=1, le=60),
    interval: str = Query(default="1D", description="bar grain: 1m..1H, 1D, 1W, 1M"),
    model: str | None = Query(default=None, description="'kronos' or 'baseline'"),
    persist: bool = Query(default=True),
    session: AsyncSession = Depends(get_session),
) -> ForecastOut:
    try:
        run = await forecast_service.run_forecast(
            session,
            symbol.upper(),
            horizon,
            interval=interval,
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
            target_time=(
                run.target_ts[i].strftime("%Y-%m-%dT%H:%M:%S")
                if run.intraday and i < len(run.target_ts)
                else None
            ),
            predicted_close=run.result.predictions[i],
        )
        for i in range(len(run.result.predictions))
    ]
    return ForecastOut(
        symbol=run.instrument.symbol,
        model_name=run.result.model_name,
        horizon=run.result.horizon,
        interval=run.interval,
        points=points,
        meta=run.result.meta,
    )


# --- Financial research (Phase 5) -------------------------------------------


@router.get("/{symbol}/profile")
async def get_profile(
    symbol: str,
    auth: Annotated[AuthContext, Depends(get_auth)],
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Company profile + business summary (yfinance, cached; degrades to DB)."""
    try:
        data = await research.get_fundamentals(session, symbol)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "symbol": symbol.upper(),
        "profile": data["profile"],
        "fetched_at": data["fetched_at"],
        "source": data["source"],
    }


@router.get("/{symbol}/financials")
async def get_financials(
    symbol: str,
    auth: Annotated[AuthContext, Depends(get_auth)],
    period: str = Query(default="annual", pattern="^(annual|quarterly)$"),
    statement: str = Query(default="income", pattern="^(income|balance|cashflow)$"),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Financial statements (annual/quarterly income, balance sheet, cashflow)."""
    try:
        data = await research.get_fundamentals(session, symbol)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if statement == "income":
        stmt = data["income_quarterly"] if period == "quarterly" else data["income_annual"]
    elif statement == "balance":
        stmt = data["balance_sheet"]  # annual only from yfinance
    else:
        stmt = data["cashflow"]  # annual only from yfinance
    return {
        "symbol": symbol.upper(),
        "period": period,
        "statement": statement,
        "data": stmt,
        "fetched_at": data["fetched_at"],
        "source": data["source"],
    }


@router.get("/{symbol}/earnings")
async def get_earnings(
    symbol: str,
    auth: Annotated[AuthContext, Depends(get_auth)],
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Earnings analysis derived from quarterly income (trend + QoQ/YoY growth)."""
    try:
        data = await research.get_fundamentals(session, symbol)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    analysis = research.derive_earnings(data["income_quarterly"])
    return {
        "symbol": symbol.upper(),
        **analysis,
        "fetched_at": data["fetched_at"],
        "source": data["source"],
    }
