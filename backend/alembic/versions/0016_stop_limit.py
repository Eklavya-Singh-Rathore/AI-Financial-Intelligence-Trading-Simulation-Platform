"""widen sim_orders.order_type for stop-limit (Phase 6.5)

Stop-limit orders (``order_type='stop_limit'``, 10 chars) don't fit the original
``VARCHAR(8)``. Widen the column to ``VARCHAR(16)``. Idempotent + vanilla-
Postgres safe (guarded on the table existing).

Revision ID: 0016_stop_limit
Revises: 0015_ingest_jobs
Create Date: 2026-07-20
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0016_stop_limit"
down_revision: str | None = "0015_ingest_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_table() -> bool:
    bind = op.get_bind()
    return bind.execute(sa.text("select to_regclass('public.sim_orders')")).scalar() is not None


def upgrade() -> None:
    if not _has_table():
        return
    op.alter_column(
        "sim_orders",
        "order_type",
        type_=sa.String(16),
        existing_type=sa.String(8),
        existing_nullable=False,
    )


def downgrade() -> None:
    if not _has_table():
        return
    op.alter_column(
        "sim_orders",
        "order_type",
        type_=sa.String(8),
        existing_type=sa.String(16),
        existing_nullable=False,
    )
