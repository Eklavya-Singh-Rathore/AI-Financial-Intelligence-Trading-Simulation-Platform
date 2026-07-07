"""Instrument model - maps the PRE-EXISTING ``instruments`` table (read-only use).

Enum columns (instrument_type, status) map onto the existing PG enum types with
``create_type=False`` (never emit DDL for them). Plain-string mapping breaks
under asyncpg's typed prepared statements: ``operator does not exist:
instrument_status = character varying``. The table is owned by prior
migrations; we never create or mutate it here.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, String
from sqlalchemy.dialects.postgresql import ENUM, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Existing PG enum types (labels mirrored from the live schema; DDL never emitted).
instrument_type_enum = ENUM(
    "equity", "index", "commodity", "etf", "bond", "mutual_fund",
    "forex", "crypto", "future", "option",
    name="instrument_type", create_type=False,
)
instrument_status_enum = ENUM(
    "active", "delisted", "suspended", name="instrument_status", create_type=False
)


class Instrument(Base):
    __tablename__ = "instruments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    isin: Mapped[str | None] = mapped_column(String, nullable=True)
    instrument_type: Mapped[str] = mapped_column(instrument_type_enum, nullable=False)
    exchange_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    currency: Mapped[str] = mapped_column(String, nullable=False)
    country: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(instrument_status_enum, nullable=False)
    listing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Instrument {self.symbol} ({self.instrument_type})>"
