"""user watchlists (Phase 6)

Adds watchlists / watchlist_items so users can group instruments ahead of the
market expansion (dashboard tabs filter by watchlist). Same conventions as
0011: UUID PKs, timestamptz, RLS enabled deny-by-default, vanilla-Postgres
safe. Per-owner name uniqueness uses a COALESCE expression index so the NULL
(service) owner is bounded too.

Revision ID: 0014_watchlists
Revises: 0013_run_context
Create Date: 2026-07-18
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0014_watchlists"
down_revision: str | None = "0013_run_context"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "watchlists",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=64), nullable=False, server_default="Watchlist"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_watchlists_user_id", "watchlists", ["user_id"])
    op.execute(
        "CREATE UNIQUE INDEX uq_watchlists_owner_name ON watchlists "
        "((COALESCE(user_id, '00000000-0000-0000-0000-000000000000'::uuid)), name)"
    )

    op.create_table(
        "watchlist_items",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "watchlist_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("watchlists.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "instrument_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("instruments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("watchlist_id", "instrument_id", name="uq_watchlist_items_list_inst"),
    )
    op.create_index("ix_watchlist_items_watchlist", "watchlist_items", ["watchlist_id"])

    for table in ("watchlists", "watchlist_items"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_index("ix_watchlist_items_watchlist", table_name="watchlist_items")
    op.drop_table("watchlist_items")
    op.execute("DROP INDEX IF EXISTS uq_watchlists_owner_name")
    op.drop_index("ix_watchlists_user_id", table_name="watchlists")
    op.drop_table("watchlists")
