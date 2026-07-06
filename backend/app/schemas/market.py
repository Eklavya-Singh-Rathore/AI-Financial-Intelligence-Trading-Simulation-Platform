"""Pydantic schemas for instruments, price bars, indicators, and ingestion."""

from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class InstrumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    symbol: str
    display_name: str
    instrument_type: str
    currency: str
    country: str
    status: str


class PriceBarOut(BaseModel):
    date: date
    open: float
    high: float
    low: float
    close: float
    adj_close: float | None = None
    volume: int


class PriceSeriesOut(BaseModel):
    symbol: str
    count: int
    bars: list[PriceBarOut]


class IndicatorPoint(BaseModel):
    date: date
    values: dict[str, float | None]


class IndicatorSeriesOut(BaseModel):
    symbol: str
    indicators: list[str]
    count: int
    points: list[IndicatorPoint]


class IngestRequest(BaseModel):
    symbols: list[str] | None = Field(
        default=None, description="Subset of instrument symbols; omit for the whole universe."
    )
    days: int | None = Field(default=None, ge=1, description="Look-back window in days.")
    start: date | None = None
    end: date | None = None


class InstrumentIngestOut(BaseModel):
    symbol: str
    provider_symbol: str
    fetched: int
    inserted: int
    skipped: int
    error: str | None = None


class IngestSummaryOut(BaseModel):
    total_instruments: int
    total_inserted: int
    total_fetched: int
    results: list[InstrumentIngestOut]
