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
from sqlalchemy import text

from app.core.config import get_settings
from app.db.base import get_engine, get_sessionmaker
from app.services import data_ingest

log = structlog.get_logger(__name__)

_scheduler: AsyncIOScheduler | None = None

# Cluster-wide advisory lock key for the daily ingest (any stable int64).
DAILY_INGEST_LOCK_KEY = 815_001


async def daily_ingest_job() -> None:
    """Fetch the last 7 days of bars for every active instrument.

    A Postgres advisory lock makes the job single-flight across replicas /
    multiple workers (audit MED-5): whoever fails to take the lock skips.
    """
    engine = get_engine()
    async with engine.connect() as lock_conn:
        got_lock = (
            await lock_conn.execute(
                text("SELECT pg_try_advisory_lock(:key)"), {"key": DAILY_INGEST_LOCK_KEY}
            )
        ).scalar()
        if not got_lock:
            log.info("daily_ingest_skipped", reason="another instance holds the lock")
            return
        try:
            log.info("daily_ingest_started")
            sm = get_sessionmaker()
            async with sm() as session:
                summary = await data_ingest.ingest_all(session, days=7)
            log.info(
                "daily_ingest_finished",
                instruments=summary.total_instruments,
                inserted=summary.total_inserted,
            )
        except Exception as exc:  # noqa: BLE001 - a failed job must not kill the app
            log.error("daily_ingest_failed", error=str(exc), exc_info=True)
        finally:
            await lock_conn.execute(
                text("SELECT pg_advisory_unlock(:key)"), {"key": DAILY_INGEST_LOCK_KEY}
            )


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
