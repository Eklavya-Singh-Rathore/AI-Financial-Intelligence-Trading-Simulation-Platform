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
    payload: dict = {
        "status": "ok",
        "env": settings.env,
        "database": db_status,
        "kronos_mode": settings.kronos_mode,
        "embeddings_mode": settings.embeddings_mode,
        "default_forecaster": settings.default_forecaster,
        # Configured Kronos checkpoint (Phase 6 audit): local mode loads these
        # directly; remote mode passes them to the Space as defaults.
        "kronos_model_id": settings.kronos_model_id,
        "kronos_tokenizer_id": settings.kronos_tokenizer_id,
        "kronos_max_context": settings.kronos_max_context,
        "embedding_model_id": settings.embedding_model_id,
    }
    # In remote mode, report what the Space last said it had loaded (from the
    # keepalive job's cached /health ping — never a blocking request here).
    if settings.kronos_mode == "remote" or settings.embeddings_mode == "remote":
        from app.services.space_client import get_space_client

        cached = get_space_client().last_health
        if cached is not None:
            payload["remote_inference"] = {
                "kronos_model_id": cached.get("kronos_model_id"),
                "kronos_tokenizer_id": cached.get("kronos_tokenizer_id"),
                "embedding_model_id": cached.get("embedding_model_id"),
                "device": cached.get("device"),
                "app_version": cached.get("app_version"),
            }
        else:
            payload["remote_inference"] = None
    return payload
