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
    # ISO string: a date ("2026-07-17") for daily/weekly/monthly, or naive
    # exchange-local datetime ("2026-07-20T09:15:00") for intraday (Phase 6.5).
    date: str
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
    date: str  # ISO date (daily) or datetime (intraday) — matches PriceBarOut
    values: dict[str, float | None]


class IndicatorSeriesOut(BaseModel):
    symbol: str
    indicators: list[str]
    count: int
    points: list[IndicatorPoint]


class InstrumentSummaryOut(BaseModel):
    symbol: str
    display_name: str
    instrument_type: str
    last_date: date | None = None
    last_close: float | None = None
    change_1d_pct: float | None = None
    change_5d_pct: float | None = None
    change_20d_pct: float | None = None
    sparkline: list[float] = Field(default_factory=list)


class UniverseSummaryOut(BaseModel):
    """Paged dashboard payload (Phase 6): items + total matching count."""

    items: list[InstrumentSummaryOut]
    total: int


class IngestRequest(BaseModel):
    symbols: list[str] | None = Field(
        default=None, description="Subset of instrument symbols; omit for the whole universe."
    )
    days: int | None = Field(default=None, ge=1, description="Look-back window in days.")
    start: date | None = None
    end: date | None = None
    background: bool = Field(
        default=False,
        description="Run the ingest in the background; response has status='started'.",
    )


class InstrumentIngestOut(BaseModel):
    symbol: str
    provider_symbol: str
    fetched: int
    inserted: int
    skipped: int
    error: str | None = None


class IngestSummaryOut(BaseModel):
    status: str = "completed"  # completed | started (background mode)
    total_instruments: int
    total_inserted: int
    total_fetched: int
    results: list[InstrumentIngestOut]
