"""add forecasts and backtests tables

Additive migration owned by this project. Continues from the existing DB head
(0004_warehouse) and follows the established conventions: UUID PKs, timestamptz
columns, JSONB, and RLS enabled deny-by-default (the backend connects as the
table owner and bypasses non-forced RLS).

Revision ID: 0005_forecasts_backtests
Revises: 0004_warehouse
Create Date: 2026-07-06
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005_forecasts_backtests"
down_revision: str | None = "0004_warehouse"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Precondition guard (audit MED-8): this chain ASSUMES the pre-existing
    # base schema (instruments, price_bars, ...) owned by the prior repository.
    # On a fresh database, load scripts/base_schema.sql first - otherwise the
    # FK below fails with a confusing error.
    bind = op.get_bind()
    exists = bind.execute(
        sa.text("SELECT to_regclass('public.instruments') IS NOT NULL")
    ).scalar()
    if not exists:
        raise RuntimeError(
            "Base table 'instruments' is missing. This migration chain extends a "
            "pre-existing schema; bootstrap a fresh database with "
            "scripts/base_schema.sql before running 'alembic upgrade head'."
        )

    op.create_table(
        "forecasts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "instrument_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("instruments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("model_name", sa.String(length=64), nullable=False),
        sa.Column("horizon", sa.Integer(), nullable=False),
        sa.Column("step", sa.Integer(), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=False),
        sa.Column("predicted_close", sa.Numeric(), nullable=False),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_forecasts_instrument_generated",
        "forecasts",
        ["instrument_id", "generated_at"],
    )

    op.create_table(
        "backtests",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("strategy_name", sa.String(length=64), nullable=False),
        sa.Column("engine", sa.String(length=32), nullable=False, server_default="nautilus"),
        sa.Column("symbols", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "params",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column(
            "metrics",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # Match the DB-wide security posture: RLS enabled, no policies (deny by
    # default for anon/authenticated; the postgres owner still has access).
    op.execute("ALTER TABLE forecasts ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE backtests ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_table("backtests")
    op.drop_index("ix_forecasts_instrument_generated", table_name="forecasts")
    op.drop_table("forecasts")
