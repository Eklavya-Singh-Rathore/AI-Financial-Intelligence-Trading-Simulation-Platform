"""financial research + news-RAG tables (Phase 5)

Adds instrument_fundamentals (yfinance profile/statement cache, TTL-refreshed)
and research_documents (retrievable corpus - news headlines this phase - with
384-d pgvector embeddings for cosine KNN + chat citations). Plain additive
tables; RLS enabled deny-by-default; runs on vanilla Postgres (pgvector
extension is present in CI's image and Supabase).

Revision ID: 0012_research
Revises: 0011_simulation
Create Date: 2026-07-12
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0012_research"
down_revision: str | None = "0011_simulation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "instrument_fundamentals",
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
            unique=True,
        ),
        sa.Column("profile", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("income_annual", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("income_quarterly", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("balance_sheet", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("cashflow", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )

    op.create_table(
        "research_documents",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("symbol", sa.String(length=32), nullable=True),
        sa.Column("doc_type", sa.String(length=24), nullable=False, server_default="news"),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_research_documents_symbol", "research_documents", ["symbol"])
    # 384-d embedding column via raw SQL (pgvector type).
    op.execute("ALTER TABLE research_documents ADD COLUMN embedding vector(384)")

    for table in ("instrument_fundamentals", "research_documents"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_index("ix_research_documents_symbol", table_name="research_documents")
    op.drop_table("research_documents")
    op.drop_table("instrument_fundamentals")
