"""revoke public EXECUTE on the admin-grant trigger function (Phase 4.6 hardening)

``public.grant_admin_role()`` (migration 0009) is a ``SECURITY DEFINER``
function used only as a ``BEFORE INSERT`` trigger on ``auth.users``. Supabase's
database linter flags that ``anon`` / ``authenticated`` can invoke it directly
via PostgREST RPC (``/rest/v1/rpc/grant_admin_role``). It references ``NEW`` and
therefore errors outside trigger context, so direct execution is never
intended — revoke it. Guarded so this is a clean no-op on a vanilla Postgres
(CI integration DB, local compose) where the function and the Supabase
``anon``/``authenticated`` roles do not exist.

Revision ID: 0010_revoke_admin_execute
Revises: 0009_user_ownership
Create Date: 2026-07-11
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0010_revoke_admin_execute"
down_revision: str | None = "0009_user_ownership"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FN_EXISTS = """
    SELECT 1 FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'public' AND p.proname = 'grant_admin_role'
"""


def upgrade() -> None:
    op.execute(
        f"""
        DO $do$
        BEGIN
            IF EXISTS ({_FN_EXISTS}) THEN
                EXECUTE 'REVOKE EXECUTE ON FUNCTION public.grant_admin_role() FROM PUBLIC';
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
                    EXECUTE 'REVOKE EXECUTE ON FUNCTION public.grant_admin_role() FROM anon';
                END IF;
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
                    EXECUTE 'REVOKE EXECUTE ON FUNCTION public.grant_admin_role() FROM authenticated';
                END IF;
            END IF;
        END
        $do$;
        """
    )


def downgrade() -> None:
    op.execute(
        f"""
        DO $do$
        BEGIN
            IF EXISTS ({_FN_EXISTS}) THEN
                EXECUTE 'GRANT EXECUTE ON FUNCTION public.grant_admin_role() TO PUBLIC';
            END IF;
        END
        $do$;
        """
    )
