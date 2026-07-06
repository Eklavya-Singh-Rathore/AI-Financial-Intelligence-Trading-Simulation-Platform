"""Pydantic schemas for backtesting endpoints."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class BacktestRequest(BaseModel):
    symbol: str = Field(description="Instrument symbol to backtest, e.g. 'RELIANCE'.")
    strategy: str = "sma_crossover"
    engine: str = Field(default="nautilus", description="Backtest engine: 'nautilus' or 'simple'.")
    start: date | None = None
    end: date | None = None
    initial_cash: float = Field(default=1_000_000.0, gt=0)
    params: dict = Field(
        default_factory=lambda: {"fast": 10, "slow": 30},
        description="Strategy parameters, e.g. {'fast': 10, 'slow': 30}.",
    )


class BacktestResultOut(BaseModel):
    strategy_name: str
    engine: str
    symbol: str
    start: date | None = None
    end: date | None = None
    metrics: dict
    meta: dict = {}
