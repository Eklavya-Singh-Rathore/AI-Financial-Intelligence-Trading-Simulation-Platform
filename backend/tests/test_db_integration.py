"""Database integration tests (audit MED-6).

Run only when DATABASE_URL is configured (CI provides a pgvector Postgres with
scripts/base_schema.sql + `alembic upgrade head` applied). Locally without a
database they skip. LLM_PROVIDER must be `fake` (CI sets it) so agent-pipeline
tests are free and deterministic.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
import pytest_asyncio
from app.core.config import get_settings
from app.db.base import dispose_engine, get_sessionmaker
from app.models.agent_run import AgentMessage, AgentRun
from app.models.instrument import Instrument
from app.models.provider import DataProvider
from app.services.data_ingest import normalize_bars, upsert_price_bars
from sqlalchemy import select, text

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
    """Fresh engine per test: pytest-asyncio gives each test its own event
    loop, and asyncpg pool connections are loop-bound ('Event loop is closed'
    otherwise). Cross-loop disposal errors are irrelevant - suppress them."""
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
    """Idempotently seed one exchange/instrument/provider/mapping + 80 bars."""
    await session.execute(
        text(
            "INSERT INTO exchanges (id, code, name, country, timezone, currency) "
            "VALUES (:id, 'TEST', 'Test Exchange', 'IN', 'Asia/Kolkata', 'INR') "
            "ON CONFLICT (code) DO NOTHING"
        ),
        {"id": str(EXCHANGE_ID)},
    )
    # status='suspended': keeps the test instrument OUT of the active universe
    # (dashboard/ingest) if this suite ever runs against a shared database.
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
    await session.execute(
        text(
            "INSERT INTO instrument_provider_mappings "
            "(id, instrument_id, provider_id, provider_symbol, is_primary, is_active) "
            "SELECT gen_random_uuid(), i.id, p.id, 'TEST.NS', TRUE, TRUE "
            "FROM instruments i, data_providers p "
            "WHERE i.symbol = :sym AND p.code = 'yfinance' "
            "ON CONFLICT ON CONSTRAINT uq_mapping_instrument_provider DO NOTHING"
        ),
        {"sym": SYMBOL},
    )
    await session.commit()

    # Resolve actual ids (rows may pre-exist from an earlier run).
    instrument = (
        await session.execute(select(Instrument).where(Instrument.symbol == SYMBOL))
    ).scalar_one()
    provider = (
        await session.execute(select(DataProvider).where(DataProvider.code == "yfinance"))
    ).scalar_one()

    # 80 synthetic daily bars (idempotent upsert).
    import numpy as np
    import pandas as pd

    n = 80
    idx = pd.bdate_range("2025-01-01", periods=n)
    close = np.linspace(100, 130, n) + 4 * np.sin(np.linspace(0, 10, n))
    df = pd.DataFrame(
        {
            "Open": close - 0.5,
            "High": close + 1.0,
            "Low": close - 1.0,
            "Close": close,
            "Adj Close": close,
            "Volume": [10_000] * n,
        },
        index=idx,
    )
    rows = normalize_bars(df, instrument.id, provider.id)
    await upsert_price_bars(session, rows)
    return instrument, provider


async def test_universe_summary_shape(session):
    """Summary returns one entry per ACTIVE instrument with the dashboard fields."""
    from app.services.market_data import universe_summary

    rows = await universe_summary(session)
    for row in rows:
        assert set(row) >= {
            "symbol", "display_name", "instrument_type", "last_date",
            "last_close", "change_1d_pct", "change_5d_pct", "change_20d_pct",
            "sparkline",
        }
        assert len(row["sparkline"]) <= 30
        assert row["symbol"] != SYMBOL  # suspended test instrument excluded


async def test_migrations_created_project_tables(session):
    result = await session.execute(
        text(
            "SELECT count(*) FROM information_schema.tables WHERE table_schema='public' "
            "AND table_name IN ('forecasts','backtests','agent_runs','agent_messages')"
        )
    )
    assert result.scalar() == 4


async def test_upsert_is_idempotent(session, seeded):
    instrument, provider = seeded
    import pandas as pd

    df = pd.DataFrame(
        {
            "Open": [10.0],
            "High": [11.0],
            "Low": [9.0],
            "Close": [10.5],
            "Adj Close": [10.4],
            "Volume": [123],
        },
        index=pd.to_datetime(["2020-06-01"]),
    )
    rows = normalize_bars(df, instrument.id, provider.id)
    first = await upsert_price_bars(session, rows)
    again = normalize_bars(df, instrument.id, provider.id)  # fresh UUIDs, same key
    second = await upsert_price_bars(session, again)
    assert first in (0, 1)  # may pre-exist from a previous CI run
    assert second == 0


async def test_session_recovers_after_db_error(session, seeded):
    """The rollback fix (HIGH-2): a failed statement must not poison the session."""
    instrument, provider = seeded
    # Snapshot plain values BEFORE the failure: rollback expires ORM objects,
    # and touching them afterwards raises MissingGreenlet (mirrors production).
    instrument_id, provider_id = instrument.id, provider.id
    bad_row = {
        "id": uuid.uuid4(),
        "instrument_id": uuid.uuid4(),  # FK violation - no such instrument
        "provider_id": provider_id,
        "date": date(2020, 1, 1),
        "timeframe": "daily",
        "open": 1.0,
        "high": 1.0,
        "low": 1.0,
        "close": 1.0,
        "adj_close": None,
        "volume": 0,
        "currency": "INR",
        "is_adjusted": False,
        "provider_version": "test",
    }
    from sqlalchemy.exc import DBAPIError, IntegrityError

    with pytest.raises((IntegrityError, DBAPIError)):
        await upsert_price_bars(session, [bad_row])
    await session.rollback()  # what ingest_instrument's handler now does

    import pandas as pd

    df = pd.DataFrame(
        {
            "Open": [20.0],
            "High": [21.0],
            "Low": [19.0],
            "Close": [20.5],
            "Adj Close": [20.4],
            "Volume": [5],
        },
        index=pd.to_datetime(["2020-07-01"]),
    )
    good = normalize_bars(df, instrument_id, provider_id)
    inserted = await upsert_price_bars(session, good)
    assert inserted in (0, 1)  # session is usable again


async def test_execute_run_completes_with_fake_llm(session, seeded):
    """Full pipeline against a real DB with the deterministic fake provider."""
    settings = get_settings()
    if settings.llm_provider != "fake":
        pytest.skip("requires LLM_PROVIDER=fake (CI sets it)")

    from app.agents.orchestrator import execute_run

    instrument, _ = seeded
    run = AgentRun(
        id=uuid.uuid4(),
        instrument_id=instrument.id,
        symbol=instrument.symbol,
        status="pending",
        trigger="test",
        debate_rounds=1,
    )
    session.add(run)
    await session.commit()

    await execute_run(session, run.id)

    refreshed = (
        await session.execute(select(AgentRun).where(AgentRun.id == run.id))
    ).scalar_one()
    assert refreshed.status == "completed", refreshed.error
    assert refreshed.final_decision is not None
    assert refreshed.final_decision["action"] in ("BUY", "SELL", "HOLD")
    assert (refreshed.token_usage or {}).get("calls", 0) >= 7
    messages = (
        (
            await session.execute(
                select(AgentMessage).where(AgentMessage.run_id == run.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(messages) >= 7


async def test_orphan_sweep_marks_stale_runs_failed(session, seeded):
    from app.agents.orchestrator import sweep_orphaned_runs

    instrument, _ = seeded
    stale = AgentRun(
        id=uuid.uuid4(),
        instrument_id=instrument.id,
        symbol=instrument.symbol,
        status="running",
        trigger="test",
        debate_rounds=1,
        created_at=datetime.now(UTC) - timedelta(hours=3),
    )
    session.add(stale)
    await session.commit()

    swept = await sweep_orphaned_runs()
    assert swept >= 1

    # The sweep ran on ANOTHER session; force re-population past the identity map.
    refreshed = (
        await session.execute(
            select(AgentRun)
            .where(AgentRun.id == stale.id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    assert refreshed.status == "failed"
    assert refreshed.error is not None and refreshed.error.startswith("orphaned")


async def test_chat_round_trip_with_fake_llm(session, seeded):
    """Create session -> send message -> both messages persisted with grounding."""
    settings = get_settings()
    if settings.llm_provider != "fake":
        pytest.skip("requires LLM_PROVIDER=fake (CI sets it)")

    from app.models.chat import ChatSession
    from app.services.chat_service import send_message

    chat = ChatSession(id=uuid.uuid4())
    session.add(chat)
    await session.commit()

    turn = await send_message(session, chat.id, "How does the market look?")
    assert turn.user_message.role == "user"
    assert turn.assistant_message.role == "assistant"
    assert turn.assistant_message.seq == turn.user_message.seq + 1
    assert turn.assistant_message.content
    assert turn.assistant_message.context is not None
    # title auto-set from the first message
    await session.refresh(chat)
    assert chat.title.startswith("How does the market look?")


async def test_multi_user_isolation(session, seeded):
    """Phase 4: users see only their own chat sessions and runs; admin sees all."""
    from app.core.auth import AuthContext
    from app.models.chat import ChatSession

    instrument, _ = seeded
    user_a, user_b = uuid.uuid4(), uuid.uuid4()

    chat_a = ChatSession(id=uuid.uuid4(), user_id=user_a, title="A's chat")
    chat_b = ChatSession(id=uuid.uuid4(), user_id=user_b, title="B's chat")
    run_a = AgentRun(
        id=uuid.uuid4(), instrument_id=instrument.id, symbol=instrument.symbol,
        user_id=user_a, status="completed", trigger="test", debate_rounds=1,
    )
    session.add_all([chat_a, chat_b, run_a])
    await session.commit()

    ctx_a = AuthContext(user_id=user_a, role="user", via="jwt")
    ctx_b = AuthContext(user_id=user_b, role="user", via="jwt")
    ctx_admin = AuthContext(user_id=uuid.uuid4(), role="admin", via="jwt")

    async def visible_chats(ctx: AuthContext) -> set[uuid.UUID]:
        stmt = select(ChatSession.id).where(
            ChatSession.id.in_([chat_a.id, chat_b.id])
        )
        if not ctx.privileged:
            stmt = stmt.where(ChatSession.user_id == ctx.user_id)
        return set((await session.execute(stmt)).scalars())

    assert await visible_chats(ctx_a) == {chat_a.id}
    assert await visible_chats(ctx_b) == {chat_b.id}
    assert await visible_chats(ctx_admin) == {chat_a.id, chat_b.id}

    async def visible_runs(ctx: AuthContext) -> set[uuid.UUID]:
        stmt = select(AgentRun.id).where(AgentRun.id == run_a.id)
        if not ctx.privileged:
            stmt = stmt.where(AgentRun.user_id == ctx.user_id)
        return set((await session.execute(stmt)).scalars())

    assert await visible_runs(ctx_a) == {run_a.id}
    assert await visible_runs(ctx_b) == set()  # cross-user run invisible
    assert await visible_runs(ctx_admin) == {run_a.id}

    # cleanup test rows
    from sqlalchemy import delete

    await session.execute(delete(ChatSession).where(ChatSession.id.in_([chat_a.id, chat_b.id])))
    await session.execute(delete(AgentRun).where(AgentRun.id == run_a.id))
    await session.commit()


async def test_idempotency_key_returns_same_run(seeded):
    """Router-level idempotent replay (MED-9) with real persistence."""
    settings = get_settings()
    if settings.llm_provider != "fake":
        pytest.skip("requires LLM_PROVIDER=fake (CI sets it)")

    from app.main import app
    from fastapi.testclient import TestClient

    key = f"it-{uuid.uuid4().hex[:16]}"
    with TestClient(app) as client:
        r1 = client.post(
            "/agents/run",
            json={"symbol": SYMBOL},
            headers={"Idempotency-Key": key},
        )
        assert r1.status_code == 202, r1.text
        r2 = client.post(
            "/agents/run",
            json={"symbol": SYMBOL},
            headers={"Idempotency-Key": key},
        )
        assert r2.status_code == 202, r2.text
        assert r1.json()["id"] == r2.json()["id"]
