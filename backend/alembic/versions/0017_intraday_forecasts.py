"""add interval + target_ts to forecasts for intraday forecasting (Phase 6.1)

Daily/weekly/monthly forecasts store a DATE target; intraday forecasts (1m..1H)
need the full timestamp. Add ``target_ts`` (nullable, naive exchange-local) and
``interval`` (bar grain, default '1D' so existing daily rows are unchanged and
the daily evaluation join keeps matching only '1D' rows). Idempotent +
vanilla-Postgres safe (guarded on the table + column presence).

Revision ID: 0017_intraday_forecasts
Revises: 0016_stop_limit
Create Date: 2026-07-21
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0017_intraday_forecasts"
down_revision: str | None = "0016_stop_limit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _forecast_columns() -> set[str]:
    bind = op.get_bind()
    if bind.execute(sa.text("select to_regclass('public.forecasts')")).scalar() is None:
        return set()  # table absent -> guarded no-op
    return {
        row[0]
        for row in bind.execute(
            sa.text(
                "select column_name from information_schema.columns "
                "where table_schema='public' and table_name='forecasts'"
            )
        )
    }


def upgrade() -> None:
    cols = _forecast_columns()
    if not cols:
        return
    if "interval" not in cols:
        op.add_column(
            "forecasts",
            sa.Column("interval", sa.String(8), nullable=False, server_default="1D"),
        )
    if "target_ts" not in cols:
        op.add_column(
            "forecasts",
            sa.Column("target_ts", sa.DateTime(timezone=False), nullable=True),
        )


def downgrade() -> None:
    cols = _forecast_columns()
    if "target_ts" in cols:
        op.drop_column("forecasts", "target_ts")
    if "interval" in cols:
        op.drop_column("forecasts", "interval")
