"""Multi-agent pipeline endpoints.

``POST /agents/run`` creates a run row and executes the pipeline in a FastAPI
background task (LLM latency makes synchronous responses impractical); clients
poll ``GET /agents/runs/{id}`` until status is ``completed``/``failed``.
"""

from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.orchestrator import execute_run
from app.db.base import get_session, get_sessionmaker
from app.models.agent_run import AgentMessage, AgentRun
from app.schemas.agents import AgentMessageOut, AgentRunOut, AgentRunRequest
from app.services import market_data

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/agents", tags=["agents"])


async def _execute_in_background(run_id: uuid.UUID) -> None:
    """Run the pipeline with a fresh session (the request session is closed)."""
    sm = get_sessionmaker()
    async with sm() as session:
        await execute_run(session, run_id)


@router.post("/run", response_model=AgentRunOut, status_code=202)
async def start_run(
    body: AgentRunRequest,
    background: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
) -> AgentRunOut:
    instrument = await market_data.get_instrument_by_symbol(session, body.symbol.upper())
    if instrument is None:
        raise HTTPException(status_code=404, detail=f"instrument '{body.symbol}' not found")

    run = AgentRun(
        id=uuid.uuid4(),
        instrument_id=instrument.id,
        symbol=instrument.symbol,
        status="pending",
        trigger="api",
        debate_rounds=body.debate_rounds,
    )
    session.add(run)
    await session.commit()
    background.add_task(_execute_in_background, run.id)
    log.info("agent_run_queued", run_id=str(run.id), symbol=instrument.symbol)
    return AgentRunOut.model_validate(run)


@router.get("/runs", response_model=list[AgentRunOut])
async def list_runs(
    limit: int = 20,
    session: AsyncSession = Depends(get_session),
) -> list[AgentRunOut]:
    result = await session.execute(
        select(AgentRun).order_by(AgentRun.created_at.desc()).limit(min(limit, 100))
    )
    return [AgentRunOut.model_validate(r) for r in result.scalars()]


async def _get_run_or_404(session: AsyncSession, run_id: uuid.UUID) -> AgentRun:
    run = (
        await session.execute(select(AgentRun).where(AgentRun.id == run_id))
    ).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail=f"run '{run_id}' not found")
    return run


@router.get("/runs/{run_id}", response_model=AgentRunOut)
async def get_run(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> AgentRunOut:
    run = await _get_run_or_404(session, run_id)
    return AgentRunOut.model_validate(run)


@router.get("/runs/{run_id}/messages", response_model=list[AgentMessageOut])
async def get_run_messages(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> list[AgentMessageOut]:
    await _get_run_or_404(session, run_id)
    result = await session.execute(
        select(AgentMessage).where(AgentMessage.run_id == run_id).order_by(AgentMessage.seq)
    )
    return [AgentMessageOut.model_validate(m) for m in result.scalars()]
