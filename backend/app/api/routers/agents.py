"""Multi-agent pipeline endpoints.

``POST /agents/run`` creates a run row and executes the pipeline in a FastAPI
background task (LLM latency makes synchronous responses impractical); clients
poll ``GET /agents/runs/{id}`` until status is ``completed``/``failed``.

Hardening (Phase 2.5):
* concurrency guard - at most ``MAX_CONCURRENT_AGENT_RUNS`` pipelines in flight
  (429 when saturated);
* per-symbol dedup - a second request while a run for the same symbol is
  pending/running returns 409 with the existing run id;
* ``Idempotency-Key`` header - repeat POSTs with the same key return the same
  run instead of spawning a duplicate paid pipeline;
* error sanitization - internal error text is only exposed when
  ``EXPOSE_ERROR_DETAILS`` is on (curated messages always pass through).
"""

from __future__ import annotations

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.orchestrator import execute_run
from app.core.auth import AuthContext, get_auth
from app.core.config import get_settings
from app.db.base import get_session, get_sessionmaker
from app.models.agent_run import AgentMessage, AgentRun
from app.schemas.agents import AgentMessageOut, AgentRunOut, AgentRunRequest
from app.services import market_data

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/agents", tags=["agents"])

Auth = Annotated[AuthContext, Depends(get_auth)]

# Error prefixes safe to show callers even with detail exposure off (curated,
# operator-authored strings - never raw exception text).
_SAFE_ERROR_PREFIXES = ("orphaned:", "run timed out")


class _RunGuard:
    """Loop-confined in-flight counter (no await between check and increment)."""

    def __init__(self) -> None:
        self.active = 0

    def try_acquire(self) -> bool:
        if self.active >= get_settings().max_concurrent_agent_runs:
            return False
        self.active += 1
        return True

    def release(self) -> None:
        self.active = max(0, self.active - 1)


_guard = _RunGuard()


def _public_run(run: AgentRun) -> AgentRunOut:
    """Serialize a run with sanitized error text (audit MED-3)."""
    out = AgentRunOut.model_validate(run)
    if (
        out.error
        and not get_settings().expose_error_details
        and not out.error.startswith(_SAFE_ERROR_PREFIXES)
    ):
        out.error = f"run failed (details in server logs; run_id={run.id})"
    return out


async def _execute_in_background(run_id: uuid.UUID) -> None:
    """Run the pipeline with a fresh session (the request session is closed)."""
    try:
        sm = get_sessionmaker()
        async with sm() as session:
            await execute_run(session, run_id)
    finally:
        _guard.release()


@router.post("/run", response_model=AgentRunOut, status_code=202)
async def start_run(
    body: AgentRunRequest,
    background: BackgroundTasks,
    auth: Auth,
    session: AsyncSession = Depends(get_session),
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
        max_length=64,
        description="Repeat POSTs with the same key return the same run.",
    ),
) -> AgentRunOut:
    # Idempotent replay: return the existing run for this key (owner-scoped).
    if idempotency_key:
        stmt = select(AgentRun).where(AgentRun.idempotency_key == idempotency_key)
        if not auth.privileged:
            stmt = stmt.where(AgentRun.user_id == auth.user_id)
        existing = (await session.execute(stmt)).scalar_one_or_none()
        if existing is not None:
            return _public_run(existing)

    instrument = await market_data.get_instrument_by_symbol(session, body.symbol.upper())
    if instrument is None:
        raise HTTPException(status_code=404, detail=f"instrument '{body.symbol}' not found")

    # Per-symbol dedup: one in-flight run per instrument PER CALLER (a user's
    # in-flight run must not block other users; service context blocks on any).
    dedup = select(AgentRun).where(
        AgentRun.symbol == instrument.symbol,
        AgentRun.status.in_(("pending", "running")),
    )
    if not auth.privileged:
        dedup = dedup.where(AgentRun.user_id == auth.user_id)
    in_flight = (await session.execute(dedup)).scalars().first()
    if in_flight is not None:
        raise HTTPException(
            status_code=409,
            detail=f"a run for '{instrument.symbol}' is already in flight: {in_flight.id}",
        )

    if not _guard.try_acquire():
        raise HTTPException(
            status_code=429,
            detail="agent-run concurrency limit reached; retry shortly",
            headers={"Retry-After": "30"},
        )

    try:
        run = AgentRun(
            id=uuid.uuid4(),
            instrument_id=instrument.id,
            symbol=instrument.symbol,
            user_id=auth.user_id,
            status="pending",
            trigger="api",
            debate_rounds=body.debate_rounds,
            idempotency_key=idempotency_key,
        )
        session.add(run)
        await session.commit()
    except IntegrityError:
        # Lost an idempotency-key race: another request created the run first.
        _guard.release()
        await session.rollback()
        race = select(AgentRun).where(AgentRun.idempotency_key == idempotency_key)
        if not auth.privileged:
            race = race.where(AgentRun.user_id == auth.user_id)
        existing = (await session.execute(race)).scalar_one_or_none()
        if existing is None:  # key collided with ANOTHER user's run -> conflict
            raise HTTPException(
                status_code=409, detail="idempotency key already in use"
            ) from None
        return _public_run(existing)
    except Exception:
        _guard.release()
        raise

    background.add_task(_execute_in_background, run.id)
    log.info("agent_run_queued", run_id=str(run.id), symbol=instrument.symbol)
    return _public_run(run)


@router.get("/runs", response_model=list[AgentRunOut])
async def list_runs(
    auth: Auth,
    limit: int = 20,
    session: AsyncSession = Depends(get_session),
) -> list[AgentRunOut]:
    stmt = select(AgentRun)
    if not auth.privileged:
        stmt = stmt.where(AgentRun.user_id == auth.user_id)
    stmt = stmt.order_by(AgentRun.created_at.desc()).limit(min(limit, 100))
    result = await session.execute(stmt)
    return [_public_run(r) for r in result.scalars()]


async def _get_run_or_404(
    session: AsyncSession, run_id: uuid.UUID, auth: AuthContext
) -> AgentRun:
    """Load a run the caller may see (cross-user access -> 404)."""
    stmt = select(AgentRun).where(AgentRun.id == run_id)
    if not auth.privileged:
        stmt = stmt.where(AgentRun.user_id == auth.user_id)
    run = (await session.execute(stmt)).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail=f"run '{run_id}' not found")
    return run


@router.get("/runs/{run_id}", response_model=AgentRunOut)
async def get_run(
    run_id: uuid.UUID,
    auth: Auth,
    session: AsyncSession = Depends(get_session),
) -> AgentRunOut:
    run = await _get_run_or_404(session, run_id, auth)
    return _public_run(run)


@router.get("/runs/{run_id}/messages", response_model=list[AgentMessageOut])
async def get_run_messages(
    run_id: uuid.UUID,
    auth: Auth,
    session: AsyncSession = Depends(get_session),
) -> list[AgentMessageOut]:
    await _get_run_or_404(session, run_id, auth)
    result = await session.execute(
        select(AgentMessage).where(AgentMessage.run_id == run_id).order_by(AgentMessage.seq)
    )
    return [AgentMessageOut.model_validate(m) for m in result.scalars()]


@router.get("/runs/{run_id}/explanation")
async def get_run_explanation(
    run_id: uuid.UUID,
    auth: Auth,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Structured explanation of the recommendation (Phase 5, no LLM call)."""
    from app.agents.explain import compose_explanation

    run = await _get_run_or_404(session, run_id, auth)
    result = await session.execute(
        select(AgentMessage).where(AgentMessage.run_id == run_id).order_by(AgentMessage.seq)
    )
    return compose_explanation(run, list(result.scalars()))
