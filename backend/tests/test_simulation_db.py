"""Simulation engine database-integration tests (Phase 5).

Run only when DATABASE_URL is configured (CI provides an ephemeral pgvector
Postgres with the schema at head). Each test uses a random owner uuid so runs
are isolated; created rows are removed at the end (cascade via portfolio).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pandas as pd
import pytest
import pytest_asyncio
from app.core.config import get_settings
from app.db.base import dispose_engine, get_sessionmaker
from app.models.agent_run import AgentRun
from app.models.instrument import Instrument
from app.models.provider import DataProvider
from app.services import simulation
from app.services.data_ingest import normalize_bars, upsert_price_bars
from app.services.simulation import SimulationError
from sqlalchemy import delete, select, text

pytestmark = [
    pytest.mark.db,
    pytest.mark.skipif(
        not get_settings().database_configured,
        reason="DATABASE_URL not configured; integration tests run in CI",
    ),
]

EXCHANGE_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")
INSTRUMENT_ID = uuid.UUID("00000000-0000-4000-8000-000000000002")
PROVIDER_ID = uuid.UUID("00000000-0000-4000-8000-000000000003")
SYMBOL = "TESTINST"


@pytest_asyncio.fixture(autouse=True)
async def _fresh_engine():
    import contextlib

    with contextlib.suppress(Exception):
        await dispose_engine()
    yield
    with contextlib.suppress(Exception):
        await dispose_engine()


@pytest_asyncio.fixture()
async def session():
    sm = get_sessionmaker()
    async with sm() as s:
        yield s


@pytest_asyncio.fixture()
async def seeded(session):
    """Same idempotent TESTINST seed as test_db_integration (suspended status)."""
    await session.execute(
        text(
            "INSERT INTO exchanges (id, code, name, country, timezone, currency) "
            "VALUES (:id, 'TEST', 'Test Exchange', 'IN', 'Asia/Kolkata', 'INR') "
            "ON CONFLICT (code) DO NOTHING"
        ),
        {"id": str(EXCHANGE_ID)},
    )
    await session.execute(
        text(
            "INSERT INTO instruments "
            "(id, symbol, display_name, instrument_type, exchange_id, currency, country, status) "
            "VALUES (:id, :sym, 'Test Instrument', 'equity', :ex, 'INR', 'IN', 'suspended') "
            "ON CONFLICT (symbol) DO NOTHING"
        ),
        {"id": str(INSTRUMENT_ID), "sym": SYMBOL, "ex": str(EXCHANGE_ID)},
    )
    await session.execute(
        text(
            "INSERT INTO data_providers (id, code, name) "
            "VALUES (:id, 'yfinance', 'Yahoo Finance') ON CONFLICT (code) DO NOTHING"
        ),
        {"id": str(PROVIDER_ID)},
    )
    await session.commit()
    instrument = (
        await session.execute(select(Instrument).where(Instrument.symbol == SYMBOL))
    ).scalar_one()
    provider = (
        await session.execute(select(DataProvider).where(DataProvider.code == "yfinance"))
    ).scalar_one()

    n = 30
    idx = pd.bdate_range("2025-06-02", periods=n)
    close = [100.0 + i for i in range(n)]  # ends at 129
    df = pd.DataFrame(
        {
            "Open": [c - 0.5 for c in close],
            "High": [c + 1.0 for c in close],
            "Low": [c - 1.0 for c in close],
            "Close": close,
            "Adj Close": close,
            "Volume": [10_000] * n,
        },
        index=idx,
    )
    await upsert_price_bars(session, normalize_bars(df, instrument.id, provider.id))
    return instrument, provider


async def _cleanup_portfolio(session, portfolio_id: uuid.UUID) -> None:
    from app.models.simulation import SimPortfolio

    await session.execute(delete(SimPortfolio).where(SimPortfolio.id == portfolio_id))
    await session.commit()


async def test_market_buy_sell_roundtrip(session, seeded):
    user = uuid.uuid4()
    portfolio = await simulation.get_or_create_portfolio(session, user)
    try:
        order = await simulation.place_order(
            session, portfolio, symbol=SYMBOL, side="buy", order_type="market", qty=10
        )
        assert order.status == "filled"
        snap = await simulation.portfolio_snapshot(session, portfolio)
        assert snap["positions"][0]["qty"] == 10
        last_close = snap["positions"][0]["last_price"]
        assert snap["cash"] == pytest.approx(float(portfolio.starting_cash) - 10 * last_close)

        sell = await simulation.place_order(
            session, portfolio, symbol=SYMBOL, side="sell", order_type="market", qty=4
        )
        assert sell.status == "filled"
        snap2 = await simulation.portfolio_snapshot(session, portfolio)
        assert snap2["positions"][0]["qty"] == 6
        # Flat price series between buy and sell -> realized P&L ~ 0.
        assert snap2["realized_pnl"] == pytest.approx(0.0, abs=0.5)
    finally:
        await _cleanup_portfolio(session, portfolio.id)


async def test_insufficient_cash_and_shares_rejected(session, seeded):
    user = uuid.uuid4()
    portfolio = await simulation.get_or_create_portfolio(session, user)
    try:
        with pytest.raises(SimulationError, match="insufficient cash"):
            await simulation.place_order(
                session, portfolio, symbol=SYMBOL, side="buy", order_type="market", qty=1_000_000
            )
        with pytest.raises(SimulationError, match="insufficient shares"):
            await simulation.place_order(
                session, portfolio, symbol=SYMBOL, side="sell", order_type="market", qty=1
            )
    finally:
        await _cleanup_portfolio(session, portfolio.id)


async def test_limit_order_rests_then_fills_on_new_bar(session, seeded):
    instrument, provider = seeded
    user = uuid.uuid4()
    # Idempotency vs persistent DBs: drop any today-bar a previous run inserted
    # (upserts are conflict-do-nothing, so it would survive and fill instantly).
    await session.execute(
        text("DELETE FROM price_bars WHERE instrument_id = :iid AND date >= :today"),
        {"iid": str(instrument.id), "today": datetime.now(UTC).date()},
    )
    await session.commit()
    portfolio = await simulation.get_or_create_portfolio(session, user)
    try:
        # Limit buy far below the market: rests open.
        order = await simulation.place_order(
            session,
            portfolio,
            symbol=SYMBOL,
            side="buy",
            order_type="limit",
            qty=5,
            limit_price=Decimal("50"),
        )
        assert order.status == "open"
        assert await simulation.sweep_open_orders(session, portfolio) == 0

        # A fresh bar (dated today) that dips to the limit triggers the fill.
        today = datetime.now(UTC).date()
        df = pd.DataFrame(
            {
                "Open": [60.0],
                "High": [61.0],
                "Low": [45.0],
                "Close": [55.0],
                "Adj Close": [55.0],
                "Volume": [5_000],
            },
            index=pd.DatetimeIndex([pd.Timestamp(today)]),
        )
        await upsert_price_bars(session, normalize_bars(df, instrument.id, provider.id))
        assert await simulation.sweep_open_orders(session, portfolio) == 1
        await session.refresh(order)
        assert order.status == "filled"
        trade_price = (
            await session.execute(
                text("SELECT price FROM sim_trades WHERE order_id = :oid"),
                {"oid": str(order.id)},
            )
        ).scalar_one()
        assert float(trade_price) == 50.0  # min(open=60, limit=50)
    finally:
        await _cleanup_portfolio(session, portfolio.id)
        await session.execute(
            text("DELETE FROM price_bars WHERE instrument_id = :iid AND date >= :today"),
            {"iid": str(instrument.id), "today": datetime.now(UTC).date()},
        )
        await session.commit()


async def test_ownership_isolation_between_users(session, seeded):
    user_a, user_b = uuid.uuid4(), uuid.uuid4()
    pa = await simulation.get_or_create_portfolio(session, user_a)
    pb = await simulation.get_or_create_portfolio(session, user_b)
    try:
        assert pa.id != pb.id
        await simulation.place_order(
            session, pa, symbol=SYMBOL, side="buy", order_type="market", qty=3
        )
        snap_b = await simulation.portfolio_snapshot(session, pb)
        assert snap_b["positions"] == []
        assert snap_b["cash"] == float(pb.starting_cash)
    finally:
        await _cleanup_portfolio(session, pa.id)
        await _cleanup_portfolio(session, pb.id)


async def test_ai_proposal_accept_flow(session, seeded):
    instrument, _ = seeded
    user = uuid.uuid4()
    portfolio = await simulation.get_or_create_portfolio(session, user)
    run = AgentRun(
        id=uuid.uuid4(),
        instrument_id=instrument.id,
        symbol=SYMBOL,
        user_id=user,
        status="completed",
        final_decision={
            "action": "BUY",
            "size_pct": 5.0,
            "confidence": 0.8,
            "summary": "test",
            "risk_verdict": "approve",
            "limited_by": [],
        },
    )
    session.add(run)
    await session.commit()
    try:
        order = await simulation.create_proposal_from_run(session, portfolio, run)
        assert order.status == "proposed"
        assert order.source == "ai"
        assert order.qty >= 1
        # AI never auto-executes: no trade until a human accepts.
        trades = (
            await session.execute(
                text("SELECT count(*) FROM sim_trades WHERE portfolio_id = :pid"),
                {"pid": str(portfolio.id)},
            )
        ).scalar_one()
        assert trades == 0

        accepted = await simulation.accept_proposal(session, portfolio, order)
        assert accepted.status == "filled"
        snap = await simulation.portfolio_snapshot(session, portfolio)
        assert snap["positions"][0]["qty"] == order.qty

        # Performance aggregates by source.
        perf = await simulation.performance(session, portfolio)
        assert perf["ai_vs_manual"]["ai"]["filled_orders"] == 1
    finally:
        await _cleanup_portfolio(session, portfolio.id)
        await session.execute(delete(AgentRun).where(AgentRun.id == run.id))
        await session.commit()


async def test_proposal_hold_rejected(session, seeded):
    instrument, _ = seeded
    user = uuid.uuid4()
    portfolio = await simulation.get_or_create_portfolio(session, user)
    run = AgentRun(
        id=uuid.uuid4(),
        instrument_id=instrument.id,
        symbol=SYMBOL,
        user_id=user,
        status="completed",
        final_decision={"action": "HOLD", "size_pct": 0.0, "confidence": 0.5, "summary": "t"},
    )
    session.add(run)
    await session.commit()
    try:
        with pytest.raises(SimulationError):
            await simulation.create_proposal_from_run(session, portfolio, run)
    finally:
        await _cleanup_portfolio(session, portfolio.id)
        await session.execute(delete(AgentRun).where(AgentRun.id == run.id))
        await session.commit()
