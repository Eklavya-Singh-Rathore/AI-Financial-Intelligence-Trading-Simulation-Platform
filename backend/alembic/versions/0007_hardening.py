"""hardening: agent_runs.idempotency_key + embeddings dedupe index

Phase 2.5 audit remediation (MED-9, LOW-2).

Revision ID: 0007_hardening
Revises: 0006_agent_runs
Create Date: 2026-07-07
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007_hardening"
down_revision: str | None = "0006_agent_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_runs",
        sa.Column("idempotency_key", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "uq_agent_runs_idempotency_key",
        "agent_runs",
        ["idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )
    # Dedupe guarantee the application logic previously only checked in code.
    op.create_index(
        "uq_agent_embeddings_source_hash",
        "agent_embeddings",
        ["source_table", "source_id", "content_hash"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_agent_embeddings_source_hash", table_name="agent_embeddings")
    op.drop_index("uq_agent_runs_idempotency_key", table_name="agent_runs")
    op.drop_column("agent_runs", "idempotency_key")
