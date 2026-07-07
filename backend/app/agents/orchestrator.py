"""Pipeline orchestrator: gather data -> run agents -> persist run + memory.

Sequencing (TradingAgents-inspired):
  gather -> technical analyst -> news analyst -> bull/bear debate (N rounds)
  -> trader -> risk manager (+ coded hard limits) -> portfolio manager.

LLM clients are synchronous; every call runs in a worker thread. Each step is
persisted as an ``agent_messages`` row as soon as it completes, so a failed run
still leaves a usable transcript.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.analysts import NewsAnalyst, TechnicalAnalyst
from app.agents.base import Agent, AgentResult
from app.agents.context import RunContext
from app.agents.portfolio import PortfolioManager
from app.agents.researchers import BearResearcher, BullResearcher
from app.agents.risk import RiskManager, apply_hard_limits
from app.agents.trader import Trader
from app.core import metrics
from app.core.config import get_settings
from app.db.base import get_sessionmaker
from app.llm.base import LLMClient
from app.llm.registry import get_llm_client
from app.ml.base import ForecasterError
from app.models.agent_run import AgentMessage, AgentRun
from app.models.instrument import Instrument
from app.services import backtest_service, embeddings, forecast_service, market_data, news
from app.services.backtest_service import BacktesterError
from app.services.indicators import compute_indicators

log = structlog.get_logger(__name__)


# --------------------------------------------------------------------------- #
# Context gathering (deterministic, no LLM)
# --------------------------------------------------------------------------- #

def _price_summary(df) -> dict:
    close = df["close"]
    last = float(close.iloc[-1])

    def ret(n: int) -> float | None:
        if len(close) <= n:
            return None
        return round((last / float(close.iloc[-n - 1]) - 1.0) * 100, 2)

    year = df.tail(252)
    return {
        "last_close": round(last, 2),
        "return_1d_pct": ret(1),
        "return_5d_pct": ret(5),
        "return_20d_pct": ret(20),
        "return_60d_pct": ret(60),
        "high_52w": round(float(year["high"].max()), 2),
        "low_52w": round(float(year["low"].min()), 2),
        "avg_volume_20d": int(df["volume"].tail(20).mean()),
        "bars_available": int(len(df)),
    }


def _latest_indicators(df) -> dict:
    values = compute_indicators(df, ["sma", "ema", "rsi", "macd", "bollinger"])
    last = values.iloc[-1]
    return {
        k: (None if last.isna()[k] else round(float(last[k]), 3)) for k in values.columns
    }


async def gather_context(session: AsyncSession, instrument: Instrument) -> RunContext:
    settings = get_settings()
    df = await market_data.price_bars_dataframe(session, instrument.id)
    if df.empty:
        raise ValueError(
            f"no price history for '{instrument.symbol}' - run POST /ingest/run first"
        )

    ctx = RunContext(
        symbol=instrument.symbol,
        display_name=instrument.display_name,
        as_of=df.index[-1].date().isoformat(),
        price_summary=_price_summary(df),
        indicators=_latest_indicators(df),
    )

    # Forecast (configured model, falling back to baseline).
    try:
        run = await forecast_service.run_forecast(
            session, instrument.symbol, horizon=5, persist=False
        )
        ctx.forecast = {
            "model": run.result.model_name,
            "horizon_days": 5,
            "predicted_closes": [round(p, 2) for p in run.result.predictions],
        }
    except ForecasterError:
        run = await forecast_service.run_forecast(
            session, instrument.symbol, horizon=5, model_name="baseline", persist=False
        )
        ctx.forecast = {
            "model": run.result.model_name,
            "horizon_days": 5,
            "predicted_closes": [round(p, 2) for p in run.result.predictions],
            "note": "configured forecaster unavailable; baseline used",
        }

    # Backtest evidence (not persisted - it's evidence, not a user request).
    try:
        bt = await backtest_service.run_backtest(
            session, symbol=instrument.symbol, engine="nautilus", persist=False
        )
        ctx.backtest = {"engine": "nautilus", "metrics": bt.result.metrics}
    except BacktesterError as exc:
        try:
            bt = await backtest_service.run_backtest(
                session, symbol=instrument.symbol, engine="simple", persist=False
            )
            ctx.backtest = {"engine": "simple", "metrics": bt.result.metrics}
        except BacktesterError:
            ctx.backtest = {"engine": "none", "error": str(exc)[:200]}

    # News headlines (best effort).
    headlines = await asyncio.to_thread(
        news.fetch_headlines, f'"{instrument.display_name}"'
    )
    ctx.headlines = [h.as_prompt_line() for h in headlines]

    # Memory: similar past conclusions for this symbol.
    ctx.memory_notes = await _recall_notes(session, instrument.symbol, settings.agent_memory_top_k)
    return ctx


async def _recall_notes(session: AsyncSession, symbol: str, top_k: int) -> list[str]:
    """Retrieve summaries of the most relevant past agent messages for a symbol."""
    try:
        hits = await embeddings.search_memory(
            session,
            f"analysis and trading decision for {symbol}",
            symbol=symbol,  # no cross-symbol contamination (audit LOW-2)
            top_k=top_k,
        )
    except Exception as exc:  # noqa: BLE001 - memory must never break a run
        log.warning("memory_search_failed", error=str(exc))
        return []
    ids: list[uuid.UUID] = []
    for h in hits:
        if h.source_table != "agent_messages":
            continue
        try:
            ids.append(uuid.UUID(h.source_id))
        except ValueError:  # malformed row must not break the run (LOW-7)
            log.warning("memory_bad_source_id", source_id=h.source_id[:64])
    if not ids:
        return []
    result = await session.execute(
        select(AgentMessage).where(AgentMessage.id.in_(ids))
    )
    notes = []
    for msg in result.scalars():
        date = msg.created_at.date().isoformat() if msg.created_at else "?"
        notes.append(f"[{date}] {msg.agent_name}: {msg.content[:300]}")
    return notes


# --------------------------------------------------------------------------- #
# Pipeline execution
# --------------------------------------------------------------------------- #

async def _step(
    session: AsyncSession,
    run: AgentRun,
    llm: LLMClient,
    agent: Agent,
    ctx: RunContext,
    seq: int,
    usage_total: dict,
) -> AgentResult:
    result = await asyncio.to_thread(agent.run, llm, ctx)
    message = AgentMessage(
        run_id=run.id,
        seq=seq,
        agent_name=result.agent_name,
        content=result.content,
        structured=result.structured,
        provider=result.response.provider,
        model=result.response.model,
        usage=result.response.usage,
        latency_ms=result.response.latency_ms,
    )
    session.add(message)
    await session.commit()
    usage_total["calls"] = usage_total.get("calls", 0) + 1
    for key in ("input_tokens", "output_tokens"):
        usage_total[key] = usage_total.get(key, 0) + int(result.response.usage.get(key, 0))
    log.info("agent_step_done", run_id=str(run.id), agent=result.agent_name, seq=seq)
    return result


async def _run_pipeline(
    session: AsyncSession,
    run: AgentRun,
    instrument: Instrument,
    usage_total: dict,
) -> None:
    """The agent pipeline proper (wrapped in a timeout by execute_run)."""
    llm = get_llm_client()
    seq = 0
    ctx = await gather_context(session, instrument)

    async def step(agent: Agent) -> AgentResult:
        nonlocal seq
        seq += 1
        return await _step(session, run, llm, agent, ctx, seq, usage_total)

    ctx.technical = (await step(TechnicalAnalyst())).structured
    ctx.sentiment = (await step(NewsAnalyst())).structured

    for _round in range(max(1, run.debate_rounds)):
        ctx.bull_arguments.append((await step(BullResearcher())).structured)
        ctx.bear_arguments.append((await step(BearResearcher())).structured)

    ctx.proposal = (await step(Trader())).structured
    ctx.risk = (await step(RiskManager())).structured

    limits = apply_hard_limits(ctx.proposal, ctx.risk, ctx.backtest)
    ctx.risk = {**ctx.risk, **limits}

    final = await step(PortfolioManager())

    # Coded limits also bind the portfolio manager's numbers.
    final_decision = dict(final.structured)
    if limits["action"] == "HOLD":
        final_decision["action"] = "HOLD"
        final_decision["size_pct"] = 0.0
    else:
        final_decision["size_pct"] = min(
            float(final_decision.get("size_pct", 0.0)), limits["size_pct"]
        )
    final_decision["risk_verdict"] = limits["risk_verdict"]
    final_decision["limited_by"] = limits["limited_by"]

    run.final_decision = final_decision
    run.token_usage = usage_total
    run.llm_provider = final.response.provider
    run.status = "completed"
    run.finished_at = datetime.now(UTC)
    await session.commit()
    log.info(
        "agent_run_completed",
        run_id=str(run.id),
        symbol=run.symbol,
        decision=final_decision.get("action"),
        size_pct=final_decision.get("size_pct"),
        **usage_total,
    )

    await _remember_run(session, run)


async def execute_run(session: AsyncSession, run_id: uuid.UUID) -> None:
    """Execute a pending AgentRun end-to-end. Owns status transitions.

    Hardening (audit HIGH-3): the pipeline runs under a wall-clock timeout, and
    the failure path rolls the session back before recording the failure so a
    mid-transaction DB error cannot strand the run in ``running``.
    """
    run = (
        await session.execute(select(AgentRun).where(AgentRun.id == run_id))
    ).scalar_one()
    instrument = (
        await session.execute(
            select(Instrument).where(Instrument.id == run.instrument_id)
        )
    ).scalar_one()

    run.status = "running"
    run.started_at = datetime.now(UTC)
    await session.commit()
    started = time.monotonic()

    usage_total: dict = {}
    timeout = get_settings().agent_run_timeout_seconds
    try:
        await asyncio.wait_for(
            _run_pipeline(session, run, instrument, usage_total), timeout=timeout
        )
        metrics.record_run_result("completed", usage_total, time.monotonic() - started)
    except TimeoutError:
        await _record_failure(
            session, run, usage_total, f"run timed out after {int(timeout)}s"
        )
        metrics.record_run_result("failed", usage_total, time.monotonic() - started)
    except Exception as exc:  # noqa: BLE001 - run must record its own failure
        await _record_failure(session, run, usage_total, str(exc)[:2000])
        metrics.record_run_result("failed", usage_total, time.monotonic() - started)


async def _record_failure(
    session: AsyncSession, run: AgentRun, usage_total: dict, error: str
) -> None:
    """Mark a run failed, tolerating a poisoned session (rollback first)."""
    try:
        await session.rollback()
        run.status = "failed"
        run.error = error
        run.token_usage = usage_total
        run.finished_at = datetime.now(UTC)
        await session.commit()
    except Exception as db_exc:  # noqa: BLE001 - last resort: fresh session
        log.error("run_failure_record_failed", run_id=str(run.id), error=str(db_exc))
        sm = get_sessionmaker()
        async with sm() as fresh:
            db_run = (
                await fresh.execute(select(AgentRun).where(AgentRun.id == run.id))
            ).scalar_one()
            db_run.status = "failed"
            db_run.error = error
            db_run.finished_at = datetime.now(UTC)
            await fresh.commit()
    log.error("agent_run_failed", run_id=str(run.id), symbol=run.symbol, error=error)


async def sweep_orphaned_runs() -> int:
    """Mark stale ``pending``/``running`` runs as failed (startup recovery).

    A crash or redeploy mid-run leaves rows in a non-terminal state with no
    worker attached (audit HIGH-3). Also purges expired memory embeddings.
    Returns the number of runs swept.
    """
    settings = get_settings()
    cutoff = datetime.now(UTC) - timedelta(minutes=settings.agent_run_stale_minutes)
    sm = get_sessionmaker()
    async with sm() as session:
        result = await session.execute(
            update(AgentRun)
            .where(
                AgentRun.status.in_(("pending", "running")),
                AgentRun.created_at < cutoff,
            )
            .values(
                status="failed",
                error="orphaned: no worker attached after restart (startup sweep)",
                finished_at=datetime.now(UTC),
            )
        )
        await session.commit()
        swept = getattr(result, "rowcount", 0) or 0
        if swept:
            log.warning("orphaned_runs_swept", count=swept)
        try:
            await embeddings.purge_expired_embeddings(session)
        except Exception as exc:  # noqa: BLE001 - purge is best-effort
            log.warning("memory_purge_failed", error=str(exc))
    return swept


async def _remember_run(session: AsyncSession, run: AgentRun) -> None:
    """Embed the run's key messages into semantic memory (best effort)."""
    try:
        result = await session.execute(
            select(AgentMessage).where(
                AgentMessage.run_id == run.id,
                AgentMessage.agent_name.in_(
                    ("technical_analyst", "news_analyst", "portfolio_manager")
                ),
            )
        )
        for msg in result.scalars():
            text = f"{run.symbol} {msg.agent_name}: {msg.content}"
            await embeddings.store_embedding(
                session,
                source_table="agent_messages",
                source_id=str(msg.id),
                text=text,
            )
    except Exception as exc:  # noqa: BLE001 - memory must never fail the run
        log.warning("memory_store_failed", run_id=str(run.id), error=str(exc))
