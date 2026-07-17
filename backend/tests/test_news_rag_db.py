"""News-RAG database-integration tests (Phase 5).

Run only when DATABASE_URL is configured. Embeddings are monkeypatched to
deterministic 384-d vectors so the tests exercise persistence + pgvector KNN
without downloading the MiniLM model or calling the inference Space. All rows
use a TESTNEWS- title prefix and are removed after each test.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from app.core.config import get_settings
from app.db.base import dispose_engine, get_sessionmaker
from app.models.research import ResearchDocument
from app.services import news_rag
from app.services.news import Headline
from sqlalchemy import delete, select

pytestmark = [
    pytest.mark.db,
    pytest.mark.skipif(
        not get_settings().database_configured,
        reason="DATABASE_URL not configured; integration tests run in CI",
    ),
]

PREFIX = "TESTNEWS-"


def _vec(hot: int) -> list[float]:
    """A unit basis vector - orthogonal per index, so KNN order is exact."""
    v = [0.0] * 384
    v[hot] = 1.0
    return v


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
        await s.execute(
            delete(ResearchDocument).where(ResearchDocument.title.like(f"{PREFIX}%"))
        )
        await s.commit()


def _headline(title: str, url: str) -> Headline:
    return Headline(
        title=f"{PREFIX}{title}",
        source="test",
        published_at="2026-07-12T08:30:00Z",
        description="desc",
        url=url,
    )


@pytest.mark.asyncio
async def test_ingest_dedupes_on_content_hash(session, monkeypatch):
    async def fake_embed(texts):
        return [_vec(0) for _ in texts]

    monkeypatch.setattr(news_rag.embeddings, "embed_texts_async", fake_embed)

    heads = [_headline("story one", "https://t.test/1"), _headline("story two", "https://t.test/2")]
    assert await news_rag.ingest_headlines(session, "TCS", heads) == 2
    # Same batch again: fully deduped.
    assert await news_rag.ingest_headlines(session, "TCS", heads) == 0
    # One old + one new: only the new row lands.
    heads.append(_headline("story three", "https://t.test/3"))
    assert await news_rag.ingest_headlines(session, "TCS", heads) == 1

    rows = (
        (
            await session.execute(
                select(ResearchDocument).where(ResearchDocument.title.like(f"{PREFIX}%"))
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 3
    assert all(r.doc_type == "news" and r.symbol == "TCS" for r in rows)


@pytest.mark.asyncio
async def test_ingest_without_embeddings_stores_null_vectors(session, monkeypatch):
    async def no_embed(texts):
        return None

    monkeypatch.setattr(news_rag.embeddings, "embed_texts_async", no_embed)

    added = await news_rag.ingest_headlines(
        session, None, [_headline("unembedded", "https://t.test/u")]
    )
    assert added == 1
    row = (
        await session.execute(
            select(ResearchDocument).where(ResearchDocument.title == f"{PREFIX}unembedded")
        )
    ).scalar_one()
    assert row.embedding is None
    assert row.symbol is None
    # NULL-embedding rows are invisible to search (which embeds via the patch).
    async def fake_embed(texts):
        return [_vec(1) for _ in texts]

    monkeypatch.setattr(news_rag.embeddings, "embed_texts_async", fake_embed)
    hits = await news_rag.search_news(session, "anything")
    assert f"{PREFIX}unembedded" not in [h.title for h in hits]


@pytest.mark.asyncio
async def test_search_orders_by_similarity_and_filters_symbol(session, monkeypatch):
    calls: list[list[str]] = []

    async def fake_embed(texts):
        calls.append(texts)
        # Ingest batch: doc0 -> basis 0, doc1 -> basis 1. Query -> basis 1.
        if len(texts) == 2:
            return [_vec(0), _vec(1)]
        return [_vec(1)]

    monkeypatch.setattr(news_rag.embeddings, "embed_texts_async", fake_embed)

    await news_rag.ingest_headlines(
        session,
        "TCS",
        [_headline("far story", "https://t.test/f"), _headline("near story", "https://t.test/n")],
    )
    hits = await news_rag.search_news(session, "query", top_k=2)
    titles = [h.title for h in hits if h.title.startswith(PREFIX)]
    assert titles[0] == f"{PREFIX}near story"  # cosine-nearest first

    # Symbol filter: no TESTNEWS docs under a different symbol.
    other = await news_rag.search_news(session, "query", symbol="RELIANCE", top_k=5)
    assert all(not h.title.startswith(PREFIX) for h in other)
