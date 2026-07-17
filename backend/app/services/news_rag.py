"""News RAG (Phase 5): durable, embedded news corpus + semantic retrieval.

Headlines already flow through the platform transiently (NewsAPI -> news
analyst prompt). This module gives them a durable home in
``research_documents`` - deduplicated by content hash, embedded with the same
MiniLM/384 vectors as agent memory - so chat can ground answers in recent news
WITH numbered citations, and later phases can extend the corpus to filings or
transcripts (``doc_type`` discriminates).

Everything here is best-effort: persistence and retrieval failures degrade to
"no news" and never break callers (same philosophy as news.py/embeddings.py).
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.research import ResearchDocument
from app.services import embeddings
from app.services.news import Headline

log = structlog.get_logger(__name__)


def headline_hash(title: str, url: str) -> str:
    """Stable dedupe key: same title from the same URL is the same story."""
    return hashlib.sha256(f"{title}|{url}".encode()).hexdigest()


def parse_published(value: str) -> datetime | None:
    """NewsAPI ISO timestamp ('2026-07-12T08:30:00Z') -> aware datetime."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def embed_text_for(doc_title: str, doc_content: str) -> str:
    """Text embedded per document: title plus description when present."""
    return f"{doc_title}. {doc_content}" if doc_content else doc_title


def citation_lines(docs: list[ResearchDocument]) -> list[str]:
    """Numbered prompt lines: '[1] [2026-07-12] Title - detail' (order kept)."""
    lines = []
    for i, doc in enumerate(docs, start=1):
        day = doc.published_at.date().isoformat() if doc.published_at else "?"
        detail = f" - {doc.content[:200]}" if doc.content else ""
        lines.append(f"[{i}] [{day}] {doc.title}{detail}")
    return lines


def citation_refs(docs: list[ResearchDocument]) -> list[dict[str, Any]]:
    """JSON-safe citation list persisted in the chat message context."""
    return [
        {
            "n": i,
            "title": doc.title,
            "url": doc.source_url,
            "published_at": doc.published_at.isoformat() if doc.published_at else None,
            "symbol": doc.symbol,
        }
        for i, doc in enumerate(docs, start=1)
    ]


async def ingest_headlines(
    session: AsyncSession, symbol: str | None, headlines: list[Headline]
) -> int:
    """Persist + embed headlines into research_documents. Returns rows added.

    Dedupes on content_hash (title|url). Embeddings are computed in one batch;
    when unavailable the rows are stored with ``embedding=NULL`` (kept for
    dedupe/history, excluded from KNN). Never raises.
    """
    if not headlines:
        return 0
    try:
        hashes = {headline_hash(h.title, h.url): h for h in headlines}
        existing = set(
            (
                await session.execute(
                    select(ResearchDocument.content_hash).where(
                        ResearchDocument.content_hash.in_(list(hashes))
                    )
                )
            )
            .scalars()
            .all()
        )
        fresh = [(digest, h) for digest, h in hashes.items() if digest not in existing]
        if not fresh:
            return 0

        vectors = await embeddings.embed_texts_async(
            [embed_text_for(h.title, h.description) for _, h in fresh]
        )
        for idx, (digest, h) in enumerate(fresh):
            session.add(
                ResearchDocument(
                    symbol=symbol.upper() if symbol else None,
                    doc_type="news",
                    title=h.title,
                    content=h.description or "",
                    source_url=h.url or None,
                    published_at=parse_published(h.published_at),
                    content_hash=digest,
                    embedding=vectors[idx] if vectors is not None else None,
                )
            )
        await session.commit()
        log.info(
            "news_ingested",
            symbol=symbol,
            added=len(fresh),
            embedded=vectors is not None,
        )
        return len(fresh)
    except Exception as exc:  # noqa: BLE001 - news persistence is best-effort
        log.warning("news_ingest_failed", symbol=symbol, error=str(exc)[:200])
        await session.rollback()
        return 0


async def search_news(
    session: AsyncSession,
    query_text: str,
    *,
    symbol: str | None = None,
    top_k: int | None = None,
) -> list[ResearchDocument]:
    """Cosine-KNN over embedded news documents; [] when retrieval is off.

    News is a shared (non-user-scoped) corpus of public headlines, so there is
    deliberately no ownership filter here.
    """
    settings = get_settings()
    top_k = top_k or settings.news_rag_top_k
    try:
        vectors = await embeddings.embed_texts_async([query_text])
        if vectors is None:
            return []
        distance = ResearchDocument.embedding.cosine_distance(vectors[0])
        stmt = (
            select(ResearchDocument)
            .where(
                ResearchDocument.doc_type == "news",
                ResearchDocument.embedding.is_not(None),
            )
            .order_by(distance)
            .limit(top_k)
        )
        if symbol:
            stmt = stmt.where(ResearchDocument.symbol == symbol.upper())
        return list((await session.execute(stmt)).scalars().all())
    except Exception as exc:  # noqa: BLE001 - retrieval must never break chat
        log.warning("news_search_failed", error=str(exc)[:200])
        return []


async def purge_old_news(session: AsyncSession) -> int:
    """Delete news documents older than NEWS_RETENTION_DAYS. Returns removed."""
    retention = get_settings().news_retention_days
    if retention <= 0:
        return 0
    cutoff = datetime.now(UTC) - timedelta(days=retention)
    result = await session.execute(
        delete(ResearchDocument).where(
            ResearchDocument.doc_type == "news",
            ResearchDocument.created_at < cutoff,
        )
    )
    await session.commit()
    removed = getattr(result, "rowcount", 0) or 0
    if removed:
        log.info("news_purged", removed=removed, retention_days=retention)
    return removed
