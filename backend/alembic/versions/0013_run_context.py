"""agent_runs.context_snapshot (Phase 5 explainability)

The orchestrator's gather step assembles the decision inputs (price summary,
indicator values, forecast, backtest, headlines) but never persisted them, so
recommendations could not be explained faithfully after the fact. This column
stores that snapshot at decision time. Nullable: old runs simply have no
snapshot and the explanation endpoint degrades to message-derived sections.

Revision ID: 0013_run_context
Revises: 0012_research
Create Date: 2026-07-17
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0013_run_context"
down_revision: str | None = "0012_research"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_runs",
        sa.Column("context_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agent_runs", "context_snapshot")
