"""whole-market lazy-load ingest jobs (Phase 6)

Adds ``ingest_jobs`` - a durable queue for background historical backfills of
newly tracked symbols. The drain worker (advisory-locked) pulls queued rows
and runs the existing per-instrument ingest, so a track request returns
immediately and the backfill survives restarts. Same conventions as prior
migrations: UUID PK, timestamptz, RLS enabled, vanilla-Postgres safe.

Revision ID: 0015_ingest_jobs
Revises: 0014_watchlists
Create Date: 2026-07-19
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0015_ingest_jobs"
down_revision: str | None = "0014_watchlists"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ingest_jobs",
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
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="backfill"),
        sa.Column("status", sa.String(length=12), nullable=False, server_default="queued"),
        sa.Column("bars_inserted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("requested_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_ingest_jobs_status_created", "ingest_jobs", ["status", "created_at"])
    op.execute("ALTER TABLE ingest_jobs ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_index("ix_ingest_jobs_status_created", table_name="ingest_jobs")
    op.drop_table("ingest_jobs")
