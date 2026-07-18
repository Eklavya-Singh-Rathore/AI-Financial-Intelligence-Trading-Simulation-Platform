"""Watchlist database-integration tests (Phase 6).

Run only when DATABASE_URL is configured (CI's pgvector Postgres or Supabase).
Random owner uuids isolate runs; rows are removed at the end (cascade).
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from app.core.config import get_settings
from app.db.base import dispose_engine, get_sessionmaker
from app.models.watchlist import Watchlist
from app.services import watchlists
from app.services.watchlists import WatchlistError
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
    """Same idempotent TESTINST seed as the other db suites."""
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
    await session.commit()
    yield
    await session.execute(delete(Watchlist).where(Watchlist.name.like("TESTWL-%")))
    await session.commit()


@pytest.mark.asyncio
async def test_crud_roundtrip_and_items(session, seeded):
    owner = uuid.uuid4()
    wl = await watchlists.create_watchlist(session, owner, "TESTWL-main")
    assert wl.user_id == owner

    # Add is idempotent.
    assert await watchlists.add_item(session, wl, SYMBOL) is True
    assert await watchlists.add_item(session, wl, SYMBOL) is False

    lists = await watchlists.list_watchlists(session, owner)
    assert [w["name"] for w in lists] == ["TESTWL-main"]
    assert lists[0]["symbols"] == [SYMBOL]

    ids = await watchlists.watchlist_instrument_ids(session, owner, wl.id)
    assert ids == [INSTRUMENT_ID]

    assert await watchlists.remove_item(session, wl, SYMBOL) is True
    assert await watchlists.remove_item(session, wl, SYMBOL) is False

    wl = await watchlists.rename_watchlist(session, wl, "TESTWL-renamed")
    assert wl.name == "TESTWL-renamed"

    await watchlists.delete_watchlist(session, wl)
    assert await watchlists.list_watchlists(session, owner) == []


@pytest.mark.asyncio
async def test_cross_user_isolation(session, seeded):
    owner_a, owner_b = uuid.uuid4(), uuid.uuid4()
    wl_a = await watchlists.create_watchlist(session, owner_a, "TESTWL-a")

    # B cannot see or resolve A's list.
    assert await watchlists.list_watchlists(session, owner_b) == []
    with pytest.raises(LookupError):
        await watchlists.get_watchlist(session, owner_b, wl_a.id)
    with pytest.raises(LookupError):
        await watchlists.watchlist_instrument_ids(session, owner_b, wl_a.id)

    await watchlists.delete_watchlist(session, wl_a)


@pytest.mark.asyncio
async def test_duplicate_name_and_unknown_symbol(session, seeded):
    owner = uuid.uuid4()
    wl = await watchlists.create_watchlist(session, owner, "TESTWL-dup")
    with pytest.raises(WatchlistError):
        await watchlists.create_watchlist(session, owner, "TESTWL-dup")
    with pytest.raises(LookupError):
        await watchlists.add_item(session, wl, "NO-SUCH-SYMBOL")
    await watchlists.delete_watchlist(session, wl)


@pytest.mark.asyncio
async def test_delete_cascades_items(session, seeded):
    owner = uuid.uuid4()
    wl = await watchlists.create_watchlist(session, owner, "TESTWL-cascade")
    await watchlists.add_item(session, wl, SYMBOL)
    wl_id = wl.id
    await watchlists.delete_watchlist(session, wl)
    from app.models.watchlist import WatchlistItem

    orphans = (
        (await session.execute(select(WatchlistItem).where(WatchlistItem.watchlist_id == wl_id)))
        .scalars()
        .all()
    )
    assert orphans == []
