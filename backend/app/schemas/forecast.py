"""Pydantic schemas for forecasting endpoints."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class ForecastPoint(BaseModel):
    step: int
    target_date: date
    predicted_close: float


class ForecastOut(BaseModel):
    symbol: str
    model_name: str
    horizon: int
    points: list[ForecastPoint]
    meta: dict = {}
