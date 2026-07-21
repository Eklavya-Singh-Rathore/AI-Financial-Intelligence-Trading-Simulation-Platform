"""Guest-workspace-reset database-integration tests (Phase 7).

Run only when DATABASE_URL is configured (CI's pgvector Postgres or Supabase).
Random owner uuids isolate runs; the reset itself removes owner_a's rows and the
teardown removes owner_b's, so nothing survives the suite.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from app.core.config import get_settings
from app.db.base import dispose_engine, get_sessionmaker
from app.models.chat import ChatMessage, ChatSession
from app.models.watchlist import Watchlist
from app.services import guest_service
from sqlalchemy import delete, func, select

pytestmark = [
    pytest.mark.db,
    pytest.mark.skipif(
        not get_settings().database_configured,
        reason="DATABASE_URL not configured; integration tests run in CI",
    ),
]


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


async def _seed_owner(session, owner: uuid.UUID) -> None:
    """Give an owner one chat session (with a message) and one watchlist."""
    chat = ChatSession(user_id=owner, title="TESTRESET-chat")
    session.add(chat)
    await session.flush()
    session.add(
        ChatMessage(session_id=chat.id, seq=1, role="user", content="hello")
    )
    session.add(Watchlist(user_id=owner, name="TESTRESET-wl"))
    await session.commit()


async def _counts(session, owner: uuid.UUID) -> tuple[int, int]:
    chats = await session.scalar(
        select(func.count()).select_from(ChatSession).where(ChatSession.user_id == owner)
    )
    lists = await session.scalar(
        select(func.count()).select_from(Watchlist).where(Watchlist.user_id == owner)
    )
    return chats or 0, lists or 0


@pytest.mark.asyncio
async def test_reset_is_scoped_to_the_caller(session):
    owner_a, owner_b = uuid.uuid4(), uuid.uuid4()
    await _seed_owner(session, owner_a)
    await _seed_owner(session, owner_b)
    try:
        assert await _counts(session, owner_a) == (1, 1)

        deleted = await guest_service.reset_workspace(session, owner_a)

        # Owner A is wiped; the returned counts reflect the deletions.
        assert await _counts(session, owner_a) == (0, 0)
        assert deleted["chat_sessions"] == 1
        assert deleted["watchlists"] == 1
        # The chat message cascaded away with its session.
        msgs = await session.scalar(
            select(func.count())
            .select_from(ChatMessage)
            .join(ChatSession, ChatMessage.session_id == ChatSession.id)
            .where(ChatSession.user_id == owner_a)
        )
        assert (msgs or 0) == 0

        # Owner B is untouched — the reset never reaches another user's data.
        assert await _counts(session, owner_b) == (1, 1)
    finally:
        await session.execute(delete(ChatSession).where(ChatSession.user_id == owner_b))
        await session.execute(delete(Watchlist).where(Watchlist.user_id == owner_b))
        await session.commit()


@pytest.mark.asyncio
async def test_reset_on_empty_workspace_is_a_noop(session):
    owner = uuid.uuid4()
    deleted = await guest_service.reset_workspace(session, owner)
    assert all(v == 0 for v in deleted.values())
    assert await _counts(session, owner) == (0, 0)
