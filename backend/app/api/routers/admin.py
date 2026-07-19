"""Admin endpoints (Phase 6): catalog reconciliation. Privileged callers only.

``GET /admin/catalog`` is a dry-run diff; ``POST /admin/catalog/sync`` applies
the curated universe (idempotent) and optionally backfills history for the
newly created symbols in the background (shared ingest mutex; the request
returns immediately).
"""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers.ingest import start_background_ingest
from app.core.auth import AuthContext, get_auth
from app.core.config import get_settings
from app.db.base import get_session
from app.services import instrument_admin

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

Auth = Annotated[AuthContext, Depends(get_auth)]


def _require_privileged(auth: AuthContext) -> None:
    if not auth.privileged:
        raise HTTPException(status_code=403, detail="admin privileges required")


class CatalogSyncRequest(BaseModel):
    backfill: bool = True
    backfill_days: int | None = Field(default=None, ge=1, le=5000)


@router.get("/catalog")
async def catalog_plan(auth: Auth, session: AsyncSession = Depends(get_session)) -> dict:
    """Dry-run: catalog size vs DB, listing missing symbols. No writes."""
    _require_privileged(auth)
    return await instrument_admin.plan_catalog(session)


@router.post("/catalog/sync")
async def catalog_sync(
    body: CatalogSyncRequest,
    background_tasks: BackgroundTasks,
    auth: Auth,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Reconcile the curated universe into the DB; backfill new symbols async."""
    _require_privileged(auth)
    summary = await instrument_admin.sync_catalog(session)
    backfill_started = False
    if body.backfill and summary.created_symbols:
        days = body.backfill_days or get_settings().default_history_days
        backfill_started = start_background_ingest(
            background_tasks, symbols=summary.created_symbols, days=days
        )
        if not backfill_started:
            log.warning("catalog_backfill_skipped", reason="ingest already running")
    return {
        "instruments_created": summary.instruments_created,
        "already_present": summary.already_present,
        "mappings_created": summary.mappings_created,
        "sectors_linked": summary.sectors_linked,
        "created_symbols": summary.created_symbols,
        "errors": summary.errors,
        "backfill_started": backfill_started,
    }
