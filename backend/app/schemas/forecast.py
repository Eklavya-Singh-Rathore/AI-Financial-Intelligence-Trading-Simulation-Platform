"""Pydantic schemas for forecasting endpoints."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class ForecastPoint(BaseModel):
    step: int
    target_date: date
    # ISO datetime (naive exchange-local) for intraday intervals; None otherwise.
    # The chart overlays on this when present, else on target_date.
    target_time: str | None = None
    predicted_close: float


class ForecastOut(BaseModel):
    symbol: str
    model_name: str
    horizon: int
    interval: str = "1D"
    points: list[ForecastPoint]
    meta: dict = {}
