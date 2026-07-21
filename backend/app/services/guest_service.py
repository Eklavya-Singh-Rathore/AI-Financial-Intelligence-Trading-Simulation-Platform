"""Reset a workspace so each guest session starts clean (Phase 7).

The guest account is shared, so on every "Continue as Guest" the frontend calls
``POST /guest/reset`` which wipes the *caller's own* data. It is self-scoped —
it can only ever delete rows owned by the authenticated user_id — so it is safe
even though the guest account is shared (concurrent guests clobber each other by
design, an accepted trade-off of the shared-guest model).

Children cascade from their user-owned parents (chat_messages, agent_messages,
sim_orders/trades/positions, watchlist_items). ``agent_embeddings`` (semantic
memory) has no user_id, so it is cleaned best-effort by the message ids it
references before those messages are deleted.
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_run import AgentEmbedding, AgentMessage, AgentRun
from app.models.backtest import Backtest
from app.models.chat import ChatMessage, ChatSession
from app.models.forecast import Forecast
from app.models.simulation import SimPortfolio
from app.models.watchlist import Watchlist


async def reset_workspace(session: AsyncSession, user_id: uuid.UUID) -> dict[str, int]:
    """Delete every workspace row owned by ``user_id``; return per-table counts."""
    counts: dict[str, int] = {}

    # Best-effort semantic-memory cleanup: embeddings key off message ids, so
    # collect the caller's message ids first, then drop the matching embeddings.
    chat_msg_ids = (
        (
            await session.execute(
                select(ChatMessage.id)
                .join(ChatSession, ChatMessage.session_id == ChatSession.id)
                .where(ChatSession.user_id == user_id)
            )
        )
        .scalars()
        .all()
    )
    run_msg_ids = (
        (
            await session.execute(
                select(AgentMessage.id)
                .join(AgentRun, AgentMessage.run_id == AgentRun.id)
                .where(AgentRun.user_id == user_id)
            )
        )
        .scalars()
        .all()
    )
    src_ids = [str(i) for i in (*chat_msg_ids, *run_msg_ids)]
    if src_ids:
        res = await session.execute(
            delete(AgentEmbedding).where(AgentEmbedding.source_id.in_(src_ids))
        )
        counts["agent_embeddings"] = getattr(res, "rowcount", 0) or 0

    # Parent deletes; intra-domain children cascade (see module docstring).
    for label, stmt in (
        ("chat_sessions", delete(ChatSession).where(ChatSession.user_id == user_id)),
        ("agent_runs", delete(AgentRun).where(AgentRun.user_id == user_id)),
        ("sim_portfolios", delete(SimPortfolio).where(SimPortfolio.user_id == user_id)),
        ("watchlists", delete(Watchlist).where(Watchlist.user_id == user_id)),
        ("forecasts", delete(Forecast).where(Forecast.user_id == user_id)),
        ("backtests", delete(Backtest).where(Backtest.user_id == user_id)),
    ):
        res = await session.execute(stmt)
        counts[label] = getattr(res, "rowcount", 0) or 0

    await session.commit()
    return counts
