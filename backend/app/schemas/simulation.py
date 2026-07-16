"""Pydantic schemas for the paper-trading (simulation) API."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class OrderCreate(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)
    side: Literal["buy", "sell"]
    order_type: Literal["market", "limit", "stop"] = "market"
    qty: int = Field(ge=1, le=1_000_000)
    limit_price: float | None = Field(default=None, gt=0)
    stop_price: float | None = Field(default=None, gt=0)


class ProposalCreate(BaseModel):
    agent_run_id: uuid.UUID


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    symbol: str
    side: str
    order_type: str
    qty: int
    limit_price: float | None = None
    stop_price: float | None = None
    status: str
    source: str
    agent_run_id: uuid.UUID | None = None
    reason: str | None = None
    created_at: datetime
    filled_at: datetime | None = None


class TradeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    order_id: uuid.UUID
    symbol: str
    side: str
    qty: int
    price: float
    value: float
    realized_pnl: float | None = None
    created_at: datetime


class PositionOut(BaseModel):
    symbol: str
    qty: int
    avg_cost: float
    last_price: float
    price_date: str | None = None
    market_value: float
    unrealized_pnl: float
    allocation_pct: float


class PortfolioOut(BaseModel):
    portfolio_id: str
    name: str
    created_at: str
    starting_cash: float
    cash: float
    buying_power: float
    holdings_value: float
    equity: float
    total_pnl: float
    total_pnl_pct: float
    realized_pnl: float
    cash_allocation_pct: float
    positions: list[PositionOut]


class EquityPoint(BaseModel):
    date: str
    equity: float
    drawdown_pct: float


class PerformanceOut(BaseModel):
    metrics: dict[str, Any]
    series: list[EquityPoint]
    ai_vs_manual: dict[str, Any]


class IntelligenceOut(BaseModel):
    risk_score: float
    portfolio_volatility_pct: float
    sector_exposure: list[dict[str, Any]]
    diversification: dict[str, Any]
    concentration: list[dict[str, Any]]
    correlation: dict[str, Any]
    suggestions: list[str]
