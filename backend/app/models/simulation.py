"""Paper-trading (simulation) models - NEW tables owned by this project (Phase 5).

One paper portfolio per user (auto-created on first access). Orders execute
against stored daily bars only - this is decision-support simulation, not a
broker. Follows existing DB conventions: UUID PKs (``gen_random_uuid()``),
timestamptz, Numeric money columns, RLS enabled deny-by-default.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

ORDER_SIDES = ("buy", "sell")
ORDER_TYPES = ("market", "limit", "stop", "stop_limit")
ORDER_STATUSES = ("proposed", "open", "filled", "cancelled", "rejected")
ORDER_SOURCES = ("manual", "ai")


class SimPortfolio(Base):
    __tablename__ = "sim_portfolios"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    # Owner (auth.users.id); NULL = service-created. Uniqueness (one portfolio
    # per owner, including the NULL service owner) is enforced by a COALESCE
    # expression unique index created in migration 0011.
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, server_default="Paper portfolio")
    starting_cash: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    cash: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<SimPortfolio {self.id} cash={self.cash}>"


class SimOrder(Base):
    __tablename__ = "sim_orders"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sim_portfolios.id", ondelete="CASCADE"), nullable=False
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("instruments.id", ondelete="CASCADE"), nullable=False
    )
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    side: Mapped[str] = mapped_column(String(4), nullable=False)  # buy | sell
    order_type: Mapped[str] = mapped_column(String(16), nullable=False)  # see ORDER_TYPES
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    limit_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    stop_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    # proposed (AI, awaiting human accept) | open (limit/stop waiting for a bar)
    # | filled | cancelled | rejected
    status: Mapped[str] = mapped_column(String(12), nullable=False, server_default="open")
    source: Mapped[str] = mapped_column(String(8), nullable=False, server_default="manual")
    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)  # rejection/cancel detail
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    filled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_sim_orders_portfolio_status", "portfolio_id", "status"),)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<SimOrder {self.side} {self.qty} {self.symbol} {self.order_type} {self.status}>"


class SimTrade(Base):
    __tablename__ = "sim_trades"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sim_orders.id", ondelete="CASCADE"), nullable=False
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sim_portfolios.id", ondelete="CASCADE"), nullable=False
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("instruments.id", ondelete="CASCADE"), nullable=False
    )
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    side: Mapped[str] = mapped_column(String(4), nullable=False)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)  # qty * price
    # Realized P&L for sells (avg-cost method); NULL for buys.
    realized_pnl: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("ix_sim_trades_portfolio_created", "portfolio_id", "created_at"),)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<SimTrade {self.side} {self.qty} {self.symbol} @ {self.price}>"


class SimPosition(Base):
    __tablename__ = "sim_positions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    portfolio_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sim_portfolios.id", ondelete="CASCADE"), nullable=False
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("instruments.id", ondelete="CASCADE"), nullable=False
    )
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    avg_cost: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)

    __table_args__ = (
        UniqueConstraint("portfolio_id", "instrument_id", name="uq_sim_positions_portfolio_inst"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<SimPosition {self.symbol} qty={self.qty} avg={self.avg_cost}>"
