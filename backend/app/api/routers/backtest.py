"""Backtesting endpoint."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.backtesting.base import BacktesterError
from app.core.auth import AuthContext, get_auth
from app.db.base import get_session
from app.schemas.backtest import BacktestRequest, BacktestResultOut
from app.services import backtest_service

router = APIRouter(prefix="/backtest", tags=["backtest"])

Auth = Annotated[AuthContext, Depends(get_auth)]


@router.post("", response_model=BacktestResultOut)
async def run_backtest(
    body: BacktestRequest,
    auth: Auth,
    session: AsyncSession = Depends(get_session),
) -> BacktestResultOut:
    """Run a strategy backtest over stored price history and persist the result."""
    try:
        run = await backtest_service.run_backtest(
            session,
            symbol=body.symbol.upper(),
            strategy=body.strategy,
            engine=body.engine,
            start=body.start,
            end=body.end,
            initial_cash=body.initial_cash,
            params=body.params.model_dump(),
            user_id=auth.user_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except BacktesterError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return BacktestResultOut(
        strategy_name=run.result.strategy_name,
        engine=run.result.engine,
        symbol=run.instrument.symbol,
        start=run.start,
        end=run.end,
        metrics=run.result.metrics,
        meta=run.result.meta,
    )
