"""Pydantic schemas for backtesting endpoints."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, model_validator


class SmaCrossoverParams(BaseModel):
    """Typed parameters for the sma_crossover strategy (audit LOW-5).

    Accepts the same JSON shape as the previous open dict, but rejects invalid
    windows at the API boundary instead of deep inside the engine.
    """

    fast: int = Field(default=10, ge=2, le=200)
    slow: int = Field(default=30, ge=3, le=400)

    @model_validator(mode="after")
    def _fast_before_slow(self) -> SmaCrossoverParams:
        if self.fast >= self.slow:
            raise ValueError("fast window must be smaller than slow window")
        return self


class BacktestRequest(BaseModel):
    symbol: str = Field(description="Instrument symbol to backtest, e.g. 'RELIANCE'.")
    strategy: str = "sma_crossover"
    engine: str = Field(default="nautilus", description="Backtest engine: 'nautilus' or 'simple'.")
    start: date | None = None
    end: date | None = None
    initial_cash: float = Field(default=1_000_000.0, gt=0)
    params: SmaCrossoverParams = Field(default_factory=SmaCrossoverParams)


class BacktestResultOut(BaseModel):
    strategy_name: str
    engine: str
    symbol: str
    start: date | None = None
    end: date | None = None
    metrics: dict
    meta: dict = {}
