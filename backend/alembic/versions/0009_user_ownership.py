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

# auth.users only exists on Supabase. On a plain Postgres (CI integration job,
# local compose) the trigger is skipped with a NOTICE - the app's role checks
# simply see no admins, which is the correct fresh-DB behaviour.
ADMIN_TRIGGER = """
DO $do$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'auth' AND table_name = 'users'
    ) THEN
        RAISE NOTICE 'auth.users not present (not a Supabase DB) - skipping admin trigger';
        RETURN;
    END IF;

    EXECUTE $fn$
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
    $fn$;
    EXECUTE 'DROP TRIGGER IF EXISTS grant_admin_role_on_signup ON auth.users';
    EXECUTE 'CREATE TRIGGER grant_admin_role_on_signup '
            'BEFORE INSERT ON auth.users '
            'FOR EACH ROW EXECUTE FUNCTION public.grant_admin_role()';
END
$do$;
"""


def upgrade() -> None:
    for table in OWNED_TABLES:
        op.add_column(table, sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True))
        op.create_index(f"ix_{table}_user_id", table, ["user_id"])
    op.execute(ADMIN_TRIGGER)


def downgrade() -> None:
    op.execute(
        """
        DO $do$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'auth' AND table_name = 'users'
            ) THEN
                EXECUTE 'DROP TRIGGER IF EXISTS grant_admin_role_on_signup ON auth.users';
            END IF;
        END
        $do$;
        """
    )
    op.execute("DROP FUNCTION IF EXISTS public.grant_admin_role()")
    for table in reversed(OWNED_TABLES):
        op.drop_index(f"ix_{table}_user_id", table_name=table)
        op.drop_column(table, "user_id")
