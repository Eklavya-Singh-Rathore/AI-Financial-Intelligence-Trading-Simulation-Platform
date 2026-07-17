"""Financial-research models (Phase 5): fundamentals cache + RAG documents."""

from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class InstrumentFundamentals(Base):
    """yfinance company profile + financial statements, cached with a TTL."""

    __tablename__ = "instrument_fundamentals"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("instruments.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    profile: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    income_annual: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    income_quarterly: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    balance_sheet: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    cashflow: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<InstrumentFundamentals {self.instrument_id}>"


class ResearchDocument(Base):
    """Retrievable research corpus with pgvector embeddings (news this phase)."""

    __tablename__ = "research_documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    symbol: Mapped[str | None] = mapped_column(String(32), nullable=True)
    doc_type: Mapped[str] = mapped_column(String(24), nullable=False, server_default="news")
    title: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(384), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("ix_research_documents_symbol", "symbol"),)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ResearchDocument {self.doc_type} {self.title[:30]}>"
