"""PriceBar model - maps the PRE-EXISTING ``price_bars`` table (read + write).

Ingestion writes daily bars here. The UUID id is generated app-side (the table
has no DB default). The natural key for idempotent upserts is
``uq_price_bars_instrument_provider_date_timeframe``
(instrument_id, provider_id, date, timeframe).
"""

from __future__ import annotations

import uuid
from datetime import date as date_type
from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import ENUM, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Existing PG enum type; create_type=False -> never emit DDL for it.
timeframe_enum = ENUM("daily", "weekly", "monthly", name="timeframe", create_type=False)


class PriceBar(Base):
    __tablename__ = "price_bars"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("instruments.id"), nullable=False
    )
    provider_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("data_providers.id"), nullable=False
    )
    date: Mapped[date_type] = mapped_column(Date, nullable=False)
    timeframe: Mapped[str] = mapped_column(timeframe_enum, nullable=False, default="daily")
    open: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    adj_close: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String, nullable=False)
    is_adjusted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    provider_version: Mapped[str | None] = mapped_column(String, nullable=True)
    source_timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ingestion_job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Column names of the natural unique key (for upsert on-conflict targets).
    NATURAL_KEY = ("instrument_id", "provider_id", "date", "timeframe")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<PriceBar instrument={self.instrument_id} date={self.date} close={self.close}>"
