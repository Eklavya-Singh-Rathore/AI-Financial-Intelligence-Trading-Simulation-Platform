"""Health/liveness endpoints."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import get_settings
from app.db.base import get_engine

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    """Liveness + database connectivity check."""
    settings = get_settings()
    db_status = "not_configured"
    if settings.database_configured:
        try:
            engine = get_engine()
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            db_status = "ok"
        except Exception as exc:  # noqa: BLE001 - report, don't crash health
            db_status = f"error: {type(exc).__name__}"
    return {
        "status": "ok",
        "env": settings.env,
        "database": db_status,
        "kronos_mode": settings.kronos_mode,
        "embeddings_mode": settings.embeddings_mode,
    }
