"""paper-trading simulation tables (Phase 5)

Adds sim_portfolios / sim_orders / sim_trades / sim_positions. Plain additive
tables following the established conventions: UUID PKs, timestamptz, Numeric
money columns, JSONB-free (all structured), RLS enabled deny-by-default. Runs
unmodified on vanilla Postgres (CI) and Supabase.

One portfolio per owner is enforced with a COALESCE expression unique index so
the NULL owner (service context) is also unique - a plain UNIQUE column would
allow unlimited NULLs.

Revision ID: 0011_simulation
Revises: 0010_revoke_admin_execute
Create Date: 2026-07-12
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0011_simulation"
down_revision: str | None = "0010_revoke_admin_execute"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sim_portfolios",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=64), nullable=False, server_default="Paper portfolio"),
        sa.Column("starting_cash", sa.Numeric(18, 2), nullable=False),
        sa.Column("cash", sa.Numeric(18, 2), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_sim_portfolios_user_id", "sim_portfolios", ["user_id"])
    op.execute(
        "CREATE UNIQUE INDEX uq_sim_portfolios_owner ON sim_portfolios "
        "((COALESCE(user_id, '00000000-0000-0000-0000-000000000000'::uuid)))"
    )

    op.create_table(
        "sim_orders",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "portfolio_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sim_portfolios.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "instrument_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("instruments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("side", sa.String(length=4), nullable=False),
        sa.Column("order_type", sa.String(length=8), nullable=False),
        sa.Column("qty", sa.Integer(), nullable=False),
        sa.Column("limit_price", sa.Numeric(18, 2), nullable=True),
        sa.Column("stop_price", sa.Numeric(18, 2), nullable=True),
        sa.Column("status", sa.String(length=12), nullable=False, server_default="open"),
        sa.Column("source", sa.String(length=8), nullable=False, server_default="manual"),
        sa.Column(
            "agent_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("filled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_sim_orders_portfolio_status", "sim_orders", ["portfolio_id", "status"])

    op.create_table(
        "sim_trades",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "order_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sim_orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "portfolio_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sim_portfolios.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "instrument_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("instruments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("side", sa.String(length=4), nullable=False),
        sa.Column("qty", sa.Integer(), nullable=False),
        sa.Column("price", sa.Numeric(18, 2), nullable=False),
        sa.Column("value", sa.Numeric(18, 2), nullable=False),
        sa.Column("realized_pnl", sa.Numeric(18, 2), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_sim_trades_portfolio_created", "sim_trades", ["portfolio_id", "created_at"])

    op.create_table(
        "sim_positions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "portfolio_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sim_portfolios.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "instrument_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("instruments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("qty", sa.Integer(), nullable=False),
        sa.Column("avg_cost", sa.Numeric(18, 4), nullable=False),
        sa.UniqueConstraint("portfolio_id", "instrument_id", name="uq_sim_positions_portfolio_inst"),
    )

    # Match the DB-wide security posture: RLS enabled, no policies.
    for table in ("sim_portfolios", "sim_orders", "sim_trades", "sim_positions"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_table("sim_positions")
    op.drop_index("ix_sim_trades_portfolio_created", table_name="sim_trades")
    op.drop_table("sim_trades")
    op.drop_index("ix_sim_orders_portfolio_status", table_name="sim_orders")
    op.drop_table("sim_orders")
    op.execute("DROP INDEX IF EXISTS uq_sim_portfolios_owner")
    op.drop_index("ix_sim_portfolios_user_id", table_name="sim_portfolios")
    op.drop_table("sim_portfolios")
