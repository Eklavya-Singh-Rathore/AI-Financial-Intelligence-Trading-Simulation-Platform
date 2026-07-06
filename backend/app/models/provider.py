"""Data-provider models - map PRE-EXISTING ``data_providers`` and
``instrument_provider_mappings`` tables (read-only use).

These let ingestion resolve, for each instrument, the correct provider-specific
symbol (e.g. the yfinance ticker ``RELIANCE.NS``) and the provider row id.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DataProvider(Base):
    __tablename__ = "data_providers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    code: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    base_url: Mapped[str | None] = mapped_column(String, nullable=True)
    is_active: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    priority: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:  # pragma: no cover
        return f"<DataProvider {self.code}>"


class InstrumentProviderMapping(Base):
    __tablename__ = "instrument_provider_mappings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("instruments.id"), nullable=False
    )
    provider_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("data_providers.id"), nullable=False
    )
    provider_symbol: Mapped[str] = mapped_column(String, nullable=False)
    is_primary: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    is_active: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Mapping {self.provider_symbol} instrument={self.instrument_id}>"
