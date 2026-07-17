"""Paper-trading (simulation) endpoints (Phase 5).

One paper portfolio per authenticated user (the service context owns the
NULL-user portfolio), auto-created on first access. All child resources are
scoped through the caller's own portfolio, so cross-user access is impossible
by construction; direct id probes return 404.

The AI never auto-executes: agent decisions arrive as ``proposed`` orders via
``POST /simulation/proposals`` and require an explicit human accept.
"""

from __future__ import annotations

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthContext, get_auth
from app.db.base import get_session
from app.models.agent_run import AgentRun
from app.models.simulation import SimOrder, SimPortfolio, SimTrade
from app.schemas.simulation import (
    IntelligenceOut,
    OrderCreate,
    OrderOut,
    PerformanceOut,
    PortfolioOut,
    ProposalCreate,
    TradeOut,
)
from app.services import simulation
from app.services.simulation import SimulationError

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/simulation", tags=["simulation"])

Auth = Annotated[AuthContext, Depends(get_auth)]


async def _portfolio(session: AsyncSession, auth: AuthContext) -> SimPortfolio:
    return await simulation.get_or_create_portfolio(session, auth.user_id)


async def _order_or_404(
    session: AsyncSession, portfolio: SimPortfolio, order_id: uuid.UUID
) -> SimOrder:
    order = (
        await session.execute(
            select(SimOrder).where(
                SimOrder.id == order_id, SimOrder.portfolio_id == portfolio.id
            )
        )
    ).scalar_one_or_none()
    if order is None:
        raise HTTPException(status_code=404, detail=f"order '{order_id}' not found")
    return order


@router.get("/portfolio", response_model=PortfolioOut)
async def get_portfolio(
    auth: Auth, session: AsyncSession = Depends(get_session)
) -> PortfolioOut:
    portfolio = await _portfolio(session, auth)
    # Lazy sweep: resting limit/stop orders are evaluated on every read so the
    # portfolio is current even between scheduler runs.
    await simulation.sweep_open_orders(session, portfolio)
    snapshot = await simulation.portfolio_snapshot(session, portfolio)
    return PortfolioOut(**snapshot)


@router.post("/orders", response_model=OrderOut, status_code=201)
async def place_order(
    payload: OrderCreate, auth: Auth, session: AsyncSession = Depends(get_session)
) -> OrderOut:
    portfolio = await _portfolio(session, auth)
    try:
        order = await simulation.place_order(
            session,
            portfolio,
            symbol=payload.symbol,
            side=payload.side,
            order_type=payload.order_type,
            qty=payload.qty,
            limit_price=_dec(payload.limit_price),
            stop_price=_dec(payload.stop_price),
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SimulationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return OrderOut.model_validate(order)


@router.get("/orders", response_model=list[OrderOut])
async def list_orders(
    auth: Auth,
    status: str | None = None,
    limit: int = 100,
    session: AsyncSession = Depends(get_session),
) -> list[OrderOut]:
    portfolio = await _portfolio(session, auth)
    stmt = select(SimOrder).where(SimOrder.portfolio_id == portfolio.id)
    if status:
        stmt = stmt.where(SimOrder.status == status)
    stmt = stmt.order_by(SimOrder.created_at.desc()).limit(min(limit, 500))
    result = await session.execute(stmt)
    return [OrderOut.model_validate(o) for o in result.scalars()]


@router.delete("/orders/{order_id}", response_model=OrderOut)
async def cancel_order(
    order_id: uuid.UUID, auth: Auth, session: AsyncSession = Depends(get_session)
) -> OrderOut:
    portfolio = await _portfolio(session, auth)
    order = await _order_or_404(session, portfolio, order_id)
    try:
        order = await simulation.reject_or_cancel(session, order, action="cancel")
    except SimulationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return OrderOut.model_validate(order)


@router.post("/orders/{order_id}/accept", response_model=OrderOut)
async def accept_order(
    order_id: uuid.UUID, auth: Auth, session: AsyncSession = Depends(get_session)
) -> OrderOut:
    portfolio = await _portfolio(session, auth)
    order = await _order_or_404(session, portfolio, order_id)
    try:
        order = await simulation.accept_proposal(session, portfolio, order)
    except SimulationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return OrderOut.model_validate(order)


@router.post("/orders/{order_id}/reject", response_model=OrderOut)
async def reject_order(
    order_id: uuid.UUID, auth: Auth, session: AsyncSession = Depends(get_session)
) -> OrderOut:
    portfolio = await _portfolio(session, auth)
    order = await _order_or_404(session, portfolio, order_id)
    try:
        order = await simulation.reject_or_cancel(session, order, action="reject")
    except SimulationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return OrderOut.model_validate(order)


@router.get("/trades", response_model=list[TradeOut])
async def list_trades(
    auth: Auth, limit: int = 200, session: AsyncSession = Depends(get_session)
) -> list[TradeOut]:
    portfolio = await _portfolio(session, auth)
    result = await session.execute(
        select(SimTrade)
        .where(SimTrade.portfolio_id == portfolio.id)
        .order_by(SimTrade.created_at.desc())
        .limit(min(limit, 1000))
    )
    return [TradeOut.model_validate(t) for t in result.scalars()]


@router.get("/performance", response_model=PerformanceOut)
async def get_performance(
    auth: Auth, session: AsyncSession = Depends(get_session)
) -> PerformanceOut:
    portfolio = await _portfolio(session, auth)
    await simulation.sweep_open_orders(session, portfolio)
    data = await simulation.performance(session, portfolio)
    return PerformanceOut(**data)


@router.get("/intelligence", response_model=IntelligenceOut)
async def get_intelligence(
    auth: Auth, session: AsyncSession = Depends(get_session)
) -> IntelligenceOut:
    portfolio = await _portfolio(session, auth)
    data = await simulation.intelligence(session, portfolio)
    return IntelligenceOut(**data)


@router.post("/proposals", response_model=OrderOut, status_code=201)
async def create_proposal(
    payload: ProposalCreate, auth: Auth, session: AsyncSession = Depends(get_session)
) -> OrderOut:
    portfolio = await _portfolio(session, auth)
    stmt = select(AgentRun).where(AgentRun.id == payload.agent_run_id)
    if not auth.privileged:
        stmt = stmt.where(AgentRun.user_id == auth.user_id)
    run = (await session.execute(stmt)).scalar_one_or_none()
    if run is None:
        raise HTTPException(
            status_code=404, detail=f"run '{payload.agent_run_id}' not found"
        )
    try:
        order = await simulation.create_proposal_from_run(session, portfolio, run)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SimulationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    log.info("sim_proposal_created", order_id=str(order.id), run_id=str(run.id))
    return OrderOut.model_validate(order)


def _dec(value: float | None):  # -> Decimal | None
    from decimal import Decimal

    return None if value is None else Decimal(str(value))
