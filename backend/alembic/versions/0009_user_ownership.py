"""per-user ownership + admin bootstrap trigger (Phase 4)

Adds nullable ``user_id`` (auth.users.id) to chat_sessions, agent_runs,
backtests, forecasts; creates an auth.users trigger that grants
app_metadata.role='admin' to the configured owner emails at sign-up.

Revision ID: 0009_user_ownership
Revises: 0008_chat
Create Date: 2026-07-07
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0009_user_ownership"
down_revision: str | None = "0008_chat"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OWNED_TABLES = ("chat_sessions", "agent_runs", "backtests", "forecasts")

ADMIN_TRIGGER = """
CREATE OR REPLACE FUNCTION public.grant_admin_role()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    IF NEW.email IN ('esr.arsenal.07@gmail.com', 'rathore.eklavya72@gmail.com') THEN
        NEW.raw_app_meta_data :=
            coalesce(NEW.raw_app_meta_data, '{}'::jsonb) || '{"role": "admin"}'::jsonb;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS grant_admin_role_on_signup ON auth.users;
CREATE TRIGGER grant_admin_role_on_signup
    BEFORE INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.grant_admin_role();
"""


def upgrade() -> None:
    for table in OWNED_TABLES:
        op.add_column(table, sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True))
        op.create_index(f"ix_{table}_user_id", table, ["user_id"])
    op.execute(ADMIN_TRIGGER)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS grant_admin_role_on_signup ON auth.users")
    op.execute("DROP FUNCTION IF EXISTS public.grant_admin_role()")
    for table in reversed(OWNED_TABLES):
        op.drop_index(f"ix_{table}_user_id", table_name=table)
        op.drop_column(table, "user_id")
