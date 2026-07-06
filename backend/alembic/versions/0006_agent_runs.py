"""add agent_runs and agent_messages tables (Phase 2 multi-agent system)

Revision ID: 0006_agent_runs
Revises: 0005_forecasts_backtests
Create Date: 2026-07-07
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006_agent_runs"
down_revision: str | None = "0005_forecasts_backtests"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_runs",
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
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("trigger", sa.String(length=16), nullable=False, server_default="api"),
        sa.Column("llm_provider", sa.String(length=32), nullable=True),
        sa.Column("debate_rounds", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("final_decision", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("token_usage", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_agent_runs_symbol_created", "agent_runs", ["symbol", "created_at"])

    op.create_table(
        "agent_messages",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("agent_name", sa.String(length=48), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("structured", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=True),
        sa.Column("model", sa.String(length=64), nullable=True),
        sa.Column("usage", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_agent_messages_run_seq", "agent_messages", ["run_id", "seq"])

    op.execute("ALTER TABLE agent_runs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE agent_messages ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_index("ix_agent_messages_run_seq", table_name="agent_messages")
    op.drop_table("agent_messages")
    op.drop_index("ix_agent_runs_symbol_created", table_name="agent_runs")
    op.drop_table("agent_runs")
