"""APScheduler jobs - daily OHLCV ingest + inference-Space keep-warm ping.

An in-process AsyncIOScheduler (no Celery, per the architecture decision). The
daily job runs after the Indian market close (configurable UTC hour/minute) and
ingests the last 7 days of bars for the whole universe - idempotent upserts make
overlap harmless. When remote inference is configured (Phase 4.5), a second
lightweight job pings the Space's /health every 6 hours so the free-tier Space
never reaches Hugging Face's ~48h idle shutdown.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import text

from app.core.config import Settings, get_settings
from app.db.base import get_engine, get_sessionmaker
from app.services import data_ingest

log = structlog.get_logger(__name__)

_scheduler: AsyncIOScheduler | None = None

# Cluster-wide advisory lock keys (any stable int64).
DAILY_INGEST_LOCK_KEY = 815_001
SIM_SWEEP_LOCK_KEY = 815_002
NEWS_INGEST_LOCK_KEY = 815_003


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


async def sim_order_sweep_job() -> None:
    """Evaluate resting limit/stop paper orders against newly ingested bars.

    Runs shortly after the daily ingest; also triggered lazily on portfolio
    reads, so this job just guarantees fills happen even for idle users.
    Advisory-locked for single-flight across replicas.
    """
    from sqlalchemy import select

    from app.models.simulation import SimOrder, SimPortfolio
    from app.services import simulation

    engine = get_engine()
    async with engine.connect() as lock_conn:
        got_lock = (
            await lock_conn.execute(
                text("SELECT pg_try_advisory_lock(:key)"), {"key": SIM_SWEEP_LOCK_KEY}
            )
        ).scalar()
        if not got_lock:
            log.info("sim_sweep_skipped", reason="another instance holds the lock")
            return
        try:
            sm = get_sessionmaker()
            async with sm() as session:
                portfolio_ids = (
                    (
                        await session.execute(
                            select(SimOrder.portfolio_id)
                            .where(SimOrder.status == "open")
                            .distinct()
                        )
                    )
                    .scalars()
                    .all()
                )
                total = 0
                for pid in portfolio_ids:
                    portfolio = (
                        await session.execute(
                            select(SimPortfolio).where(SimPortfolio.id == pid)
                        )
                    ).scalar_one_or_none()
                    if portfolio is not None:
                        total += await simulation.sweep_open_orders(session, portfolio)
                log.info(
                    "sim_sweep_finished", portfolios=len(portfolio_ids), fills=total
                )
        except Exception as exc:  # noqa: BLE001 - a failed job must not kill the app
            log.error("sim_sweep_failed", error=str(exc), exc_info=True)
        finally:
            await lock_conn.execute(
                text("SELECT pg_advisory_unlock(:key)"), {"key": SIM_SWEEP_LOCK_KEY}
            )


async def news_ingest_job() -> None:
    """Fetch + persist news headlines for every active instrument (Phase 5).

    Feeds the ``research_documents`` RAG corpus daily so chat citations do not
    depend on agent runs happening. Also purges documents older than the
    retention window. Advisory-locked; every failure is per-symbol best-effort.
    """
    from app.providers import registry as provider_registry
    from app.services import market_data, news_rag

    engine = get_engine()
    async with engine.connect() as lock_conn:
        got_lock = (
            await lock_conn.execute(
                text("SELECT pg_try_advisory_lock(:key)"), {"key": NEWS_INGEST_LOCK_KEY}
            )
        ).scalar()
        if not got_lock:
            log.info("news_ingest_skipped", reason="another instance holds the lock")
            return
        try:
            from sqlalchemy import select as sa_select

            from app.models.instrument import Instrument
            from app.models.simulation import SimPosition
            from app.models.watchlist import WatchlistItem

            sm = get_sessionmaker()
            async with sm() as session:
                instruments = await market_data.list_instruments(session)
                # Quota guard (Phase 6): held + watchlisted symbols first, the
                # rest on a deterministic daily rotation, capped.
                held = set(
                    (
                        await session.execute(
                            sa_select(Instrument.symbol).join(
                                SimPosition, SimPosition.instrument_id == Instrument.id
                            )
                        )
                    ).scalars()
                )
                watched = set(
                    (
                        await session.execute(
                            sa_select(Instrument.symbol).join(
                                WatchlistItem, WatchlistItem.instrument_id == Instrument.id
                            )
                        )
                    ).scalars()
                )
                chosen = news_rag.select_news_symbols(
                    [i.symbol for i in instruments],
                    held,
                    watched,
                    get_settings().news_ingest_daily_cap,
                    datetime.now(UTC).timetuple().tm_yday,
                )
                # Provider symbols (yfinance ticker) for the Finnhub news path.
                provider = await market_data.get_yfinance_provider(session)
                psym_map = await market_data.get_provider_symbol_map(session, provider.id)
                by_symbol = {i.symbol: i for i in instruments}
                added = 0
                for symbol in chosen:
                    inst = by_symbol[symbol]
                    # NewsAPI reads the display name (free text); Finnhub reads
                    # the provider ticker. Merged + deduped by the registry.
                    items = await asyncio.to_thread(
                        provider_registry.fetch_news,
                        f'"{inst.display_name}"',
                        symbol=psym_map.get(inst.id),
                    )
                    added += await news_rag.ingest_headlines(session, inst.symbol, items)
                purged = await news_rag.purge_old_news(session)
            log.info("news_ingest_finished", universe=len(instruments),
                     requested=len(chosen), added=added, purged=purged)
        except Exception as exc:  # noqa: BLE001 - a failed job must not kill the app
            log.error("news_ingest_failed", error=str(exc), exc_info=True)
        finally:
            await lock_conn.execute(
                text("SELECT pg_advisory_unlock(:key)"), {"key": NEWS_INGEST_LOCK_KEY}
            )


async def space_keepalive_job() -> None:
    """Ping the inference Space so it never hits the free-tier idle shutdown.

    Best-effort: a failed ping is logged and retried on the next interval.
    """
    from app.services.space_client import get_space_client

    try:
        health = await asyncio.to_thread(get_space_client().health)
        log.info("space_keepalive_ok", status=str(health.get("status", "?"))[:32])
    except Exception as exc:  # noqa: BLE001 - a failed ping must not kill the app
        log.warning("space_keepalive_failed", error=str(exc)[:200])


def _remote_inference_configured(settings: Settings) -> bool:
    modes = (settings.kronos_mode.strip().lower(), settings.embeddings_mode.strip().lower())
    return "remote" in modes and bool(settings.inference_space_url.strip())


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
    # Sweep resting paper orders ~15 min after the daily ingest lands new bars.
    sweep_minute = (settings.daily_ingest_minute + 15) % 60
    sweep_hour = (settings.daily_ingest_hour + (settings.daily_ingest_minute + 15) // 60) % 24
    scheduler.add_job(
        sim_order_sweep_job,
        CronTrigger(hour=sweep_hour, minute=sweep_minute, timezone="UTC"),
        id="sim_order_sweep",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    if settings.enable_news_ingest:
        # News RAG refresh ~30 min after the daily ingest (NewsAPI free tier
        # is 100 req/day; one request per instrument per day is well inside).
        news_minute = (settings.daily_ingest_minute + 30) % 60
        news_hour = (
            settings.daily_ingest_hour + (settings.daily_ingest_minute + 30) // 60
        ) % 24
        scheduler.add_job(
            news_ingest_job,
            CronTrigger(hour=news_hour, minute=news_minute, timezone="UTC"),
            id="news_ingest",
            replace_existing=True,
            misfire_grace_time=3600,
        )
    if _remote_inference_configured(settings):
        scheduler.add_job(
            space_keepalive_job,
            IntervalTrigger(hours=6),
            id="space_keepalive",
            replace_existing=True,
            # First ping shortly after boot warms the Space before real traffic.
            next_run_time=datetime.now(UTC) + timedelta(seconds=60),
            misfire_grace_time=3600,
        )
    scheduler.start()
    _scheduler = scheduler
    log.info(
        "scheduler_started",
        daily_ingest_utc=f"{settings.daily_ingest_hour:02d}:{settings.daily_ingest_minute:02d}",
        space_keepalive=_remote_inference_configured(settings),
        news_ingest=settings.enable_news_ingest,
    )
    return scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        log.info("scheduler_stopped")
