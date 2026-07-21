"""AI evaluation (Phase 5): how good is the AI, in numbers - no LLM calls.

Four deterministic lenses over already-persisted data:

* forecast accuracy - matured ``forecasts`` rows joined to actual closes
  (MAPE + signed bias per model);
* agent stats - status counts, action mix, average confidence, and
  technical-vs-news stance agreement over recent runs;
* recommendation success - for completed BUY/SELL runs with a context
  snapshot, is the trade direction profitable against the latest close;
* usage & cost - token totals, estimated USD cost (configurable per-1M
  prices), run wall time, and per-message latency.

Ownership follows the platform rule: non-privileged callers see their own
runs/forecasts only. Pure ``compute_*`` helpers keep the math unit-testable.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.agent_run import AgentMessage, AgentRun
from app.models.forecast import Forecast
from app.models.price_bar import PriceBar

log = structlog.get_logger(__name__)

RECENT_RUNS_LIMIT = 200


# --------------------------------------------------------------------------- #
# Pure computation helpers (unit-tested)
# --------------------------------------------------------------------------- #

def compute_forecast_accuracy(rows: list[tuple[str, float, float]]) -> dict[str, Any]:
    """rows = (model_name, predicted_close, actual_close) for matured points."""
    per_model: dict[str, dict[str, Any]] = {}
    for model, predicted, actual in rows:
        if actual is None or actual == 0:
            continue
        err_pct = (float(predicted) / float(actual) - 1.0) * 100.0
        bucket = per_model.setdefault(model, {"n": 0, "abs_sum": 0.0, "signed_sum": 0.0})
        bucket["n"] += 1
        bucket["abs_sum"] += abs(err_pct)
        bucket["signed_sum"] += err_pct
    models = {
        model: {
            "evaluated_points": b["n"],
            "mape_pct": round(b["abs_sum"] / b["n"], 2),
            "bias_pct": round(b["signed_sum"] / b["n"], 2),
        }
        for model, b in per_model.items()
    }
    return {"models": models, "evaluated_points": sum(b["n"] for b in per_model.values())}


def compute_agent_stats(
    runs: list[Any], stances: dict[uuid.UUID, dict[str, str]]
) -> dict[str, Any]:
    """Status counts, action mix, avg confidence, technical-vs-news agreement."""
    by_status: dict[str, int] = {}
    action_mix: dict[str, int] = {}
    confidences: list[float] = []
    agree = disagree = 0
    for run in runs:
        by_status[run.status] = by_status.get(run.status, 0) + 1
        if run.status != "completed":
            continue
        decision = run.final_decision or {}
        action = decision.get("action")
        if action:
            action_mix[action] = action_mix.get(action, 0) + 1
        if isinstance(decision.get("confidence"), int | float):
            confidences.append(float(decision["confidence"]))
        pair = stances.get(run.id) or {}
        tech, news = pair.get("technical_analyst"), pair.get("news_analyst")
        if tech and news:
            if tech == news:
                agree += 1
            else:
                disagree += 1
    total_pairs = agree + disagree
    return {
        "runs_by_status": by_status,
        "action_mix": action_mix,
        "avg_confidence": round(sum(confidences) / len(confidences), 3) if confidences else None,
        "stance_agreement_pct": (
            round(agree / total_pairs * 100.0, 1) if total_pairs else None
        ),
        "stance_pairs_evaluated": total_pairs,
    }


def compute_recommendation_success(
    runs: list[Any], latest_closes: dict[uuid.UUID, float]
) -> dict[str, Any]:
    """Directional P&L of completed BUY/SELL recommendations vs latest close."""
    evaluated = 0
    wins = 0
    returns: list[float] = []
    by_action: dict[str, dict[str, Any]] = {}
    for run in runs:
        if run.status != "completed":
            continue
        decision = run.final_decision or {}
        action = decision.get("action")
        if action not in ("BUY", "SELL"):
            continue
        snapshot = run.context_snapshot or {}
        entry = (snapshot.get("price_summary") or {}).get("last_close")
        current = latest_closes.get(run.instrument_id)
        if not entry or not current:
            continue
        direction = 1.0 if action == "BUY" else -1.0
        ret_pct = (float(current) / float(entry) - 1.0) * 100.0 * direction
        evaluated += 1
        returns.append(ret_pct)
        if ret_pct > 0:
            wins += 1
        bucket = by_action.setdefault(action, {"n": 0, "sum": 0.0})
        bucket["n"] += 1
        bucket["sum"] += ret_pct
    return {
        "evaluated": evaluated,
        "success_rate": round(wins / evaluated, 3) if evaluated else None,
        "avg_return_pct": round(sum(returns) / len(returns), 2) if returns else None,
        "by_action": {
            action: {"n": b["n"], "avg_return_pct": round(b["sum"] / b["n"], 2)}
            for action, b in by_action.items()
        },
    }


def compute_usage(runs: list[Any], avg_msg_latency_ms: float | None) -> dict[str, Any]:
    """Token totals, estimated cost, and timing across the runs window."""
    settings = get_settings()
    calls = input_tokens = output_tokens = 0
    durations: list[float] = []
    for run in runs:
        usage = run.token_usage or {}
        calls += int(usage.get("calls", 0) or 0)
        input_tokens += int(usage.get("input_tokens", 0) or 0)
        output_tokens += int(usage.get("output_tokens", 0) or 0)
        if run.started_at and run.finished_at:
            durations.append((run.finished_at - run.started_at).total_seconds())
    cost = (
        input_tokens / 1_000_000 * settings.llm_cost_input_per_1m
        + output_tokens / 1_000_000 * settings.llm_cost_output_per_1m
    )
    return {
        "runs_window": len(runs),
        "llm_calls": calls,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "est_cost_usd": round(cost, 4),
        "avg_run_seconds": round(sum(durations) / len(durations), 1) if durations else None,
        "avg_message_latency_ms": (
            round(avg_msg_latency_ms) if avg_msg_latency_ms is not None else None
        ),
    }


# --------------------------------------------------------------------------- #
# Data access + assembly
# --------------------------------------------------------------------------- #

async def _matured_forecast_rows(
    session: AsyncSession, owner_id: uuid.UUID | None, privileged: bool
) -> list[tuple[str, float, float]]:
    stmt = (
        select(Forecast.model_name, Forecast.predicted_close, PriceBar.close)
        .join(
            PriceBar,
            (PriceBar.instrument_id == Forecast.instrument_id)
            & (PriceBar.date == Forecast.target_date),
        )
        # Daily accuracy only: intraday/weekly/monthly forecasts (Phase 6.1) don't
        # mature against stored daily closes, so exclude them from this metric.
        .where(Forecast.interval == "1D")
    )
    if not privileged:
        stmt = stmt.where(Forecast.user_id == owner_id)
    rows = (await session.execute(stmt.limit(5000))).all()
    return [(r[0], float(r[1]), float(r[2])) for r in rows]


async def _recent_runs(
    session: AsyncSession, owner_id: uuid.UUID | None, privileged: bool
) -> list[AgentRun]:
    stmt = select(AgentRun)
    if not privileged:
        stmt = stmt.where(AgentRun.user_id == owner_id)
    stmt = stmt.order_by(AgentRun.created_at.desc()).limit(RECENT_RUNS_LIMIT)
    return list((await session.execute(stmt)).scalars().all())


async def _stances_for(
    session: AsyncSession, run_ids: list[uuid.UUID]
) -> dict[uuid.UUID, dict[str, str]]:
    if not run_ids:
        return {}
    stmt = select(
        AgentMessage.run_id,
        AgentMessage.agent_name,
        AgentMessage.structured["stance"].astext,
    ).where(
        AgentMessage.run_id.in_(run_ids),
        AgentMessage.agent_name.in_(("technical_analyst", "news_analyst")),
    )
    stances: dict[uuid.UUID, dict[str, str]] = {}
    for run_id, agent_name, stance in (await session.execute(stmt)).all():
        if stance:
            stances.setdefault(run_id, {})[agent_name] = stance
    return stances


async def _latest_closes(
    session: AsyncSession, instrument_ids: list[uuid.UUID]
) -> dict[uuid.UUID, float]:
    if not instrument_ids:
        return {}
    latest = (
        select(
            PriceBar.instrument_id,
            func.max(PriceBar.date).label("max_date"),
        )
        .where(PriceBar.instrument_id.in_(instrument_ids))
        .group_by(PriceBar.instrument_id)
        .subquery()
    )
    stmt = select(PriceBar.instrument_id, PriceBar.close).join(
        latest,
        (PriceBar.instrument_id == latest.c.instrument_id)
        & (PriceBar.date == latest.c.max_date),
    )
    return {row[0]: float(row[1]) for row in (await session.execute(stmt)).all()}


async def summary(
    session: AsyncSession, *, owner_id: uuid.UUID | None, privileged: bool
) -> dict[str, Any]:
    """The full evaluation payload for GET /evaluation/summary."""
    runs = await _recent_runs(session, owner_id, privileged)
    completed_ids = [r.id for r in runs if r.status == "completed"]
    stances = await _stances_for(session, completed_ids)
    instrument_ids = list({r.instrument_id for r in runs})
    latest_closes = await _latest_closes(session, instrument_ids)
    forecast_rows = await _matured_forecast_rows(session, owner_id, privileged)

    avg_latency = None
    if completed_ids:
        avg_latency = (
            await session.execute(
                select(func.avg(AgentMessage.latency_ms)).where(
                    AgentMessage.run_id.in_(completed_ids)
                )
            )
        ).scalar()
        avg_latency = float(avg_latency) if avg_latency is not None else None

    return {
        "forecast_accuracy": compute_forecast_accuracy(forecast_rows),
        "agents": compute_agent_stats(runs, stances),
        "recommendation_success": compute_recommendation_success(runs, latest_closes),
        "usage": compute_usage(runs, avg_latency),
    }
