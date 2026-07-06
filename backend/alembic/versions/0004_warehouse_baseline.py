"""baseline placeholder for the pre-existing schema (head = 0004_warehouse)

This project ADOPTS an existing Supabase database whose schema (instruments,
price_bars, data_providers, warehouse_*, agent_embeddings, ...) was created by a
prior repository's Alembic migrations (0001..0004_warehouse) that are not vendored
here. The live DB is already stamped ``alembic_version = 0004_warehouse``.

This empty baseline revision exists ONLY so Alembic can resolve that stamp and
build a chain forward for the tables THIS project adds. It intentionally does
nothing on upgrade/downgrade and must never be used to (re)create the base schema.

Revision ID: 0004_warehouse
Revises:
Create Date: 2026-07-06
"""
from __future__ import annotations

from collections.abc import Sequence

revision: str = "0004_warehouse"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # No-op: the base schema is externally managed and already present.
    pass


def downgrade() -> None:
    # No-op: never tear down the externally-managed base schema.
    pass
