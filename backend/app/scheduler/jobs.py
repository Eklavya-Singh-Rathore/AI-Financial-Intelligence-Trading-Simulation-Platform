"""APScheduler jobs - daily OHLCV ingest.

An in-process AsyncIOScheduler (no Celery, per the architecture decision). The
daily job runs after the Indian market close (configurable UTC hour/minute) and
ingests the last 7 days of bars for the whole universe - idempotent upserts make
overlap harmless.
"""

from __future__ import annotations

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import get_settings
from app.db.base import get_sessionmaker
from app.services import data_ingest

log = structlog.get_logger(__name__)

_scheduler: AsyncIOScheduler | None = None


async def daily_ingest_job() -> None:
    """Fetch the last 7 days of bars for every active instrument."""
    log.info("daily_ingest_started")
    try:
        sm = get_sessionmaker()
        async with sm() as session:
            summary = await data_ingest.ingest_all(session, days=7)
        log.info(
            "daily_ingest_finished",
            instruments=summary.total_instruments,
            inserted=summary.total_inserted,
        )
    except Exception as exc:  # noqa: BLE001 - a failed job must not kill the app
        log.error("daily_ingest_failed", error=str(exc))


def start_scheduler() -> AsyncIOScheduler | None:
    """Start the scheduler if enabled. Returns the scheduler (or None)."""
    global _scheduler
    settings = get_settings()
    if not settings.enable_scheduler:
        log.info("scheduler_disabled")
        return None
    if _scheduler is not None:
        return _scheduler

    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        daily_ingest_job,
        CronTrigger(
            hour=settings.daily_ingest_hour,
            minute=settings.daily_ingest_minute,
            timezone="UTC",
        ),
        id="daily_ingest",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    scheduler.start()
    _scheduler = scheduler
    log.info(
        "scheduler_started",
        daily_ingest_utc=f"{settings.daily_ingest_hour:02d}:{settings.daily_ingest_minute:02d}",
    )
    return scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        log.info("scheduler_stopped")
