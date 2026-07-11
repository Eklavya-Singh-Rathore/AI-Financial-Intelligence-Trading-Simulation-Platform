"""Semantic memory: MiniLM embeddings + pgvector search.

Uses ``all-MiniLM-L6-v2`` (384 dims - matches the pre-existing
``agent_embeddings.embedding vector(384)`` column). ``EMBEDDINGS_MODE``
selects where vectors are computed: ``local`` loads sentence-transformers
lazily in-process (~80 MB download once, cached by HF - dev default);
``remote`` calls the same model on the inference Space (production, where the
image ships without torch). All failures degrade to "memory off" behaviour:
agents run fine without memory.

Async correctness (audit CRIT-2): model load and ``encode`` are CPU-bound and
always executed via ``asyncio.to_thread`` from the async entry points here.
"""

from __future__ import annotations

import asyncio
import hashlib
import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import String, cast, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.agent_run import AgentEmbedding, AgentMessage, AgentRun

log = structlog.get_logger(__name__)

_LOCK = threading.Lock()
_MODEL: Any | None = None
_MODEL_FAILED = False

# Must match the agent_embeddings.embedding vector(384) column.
_EXPECTED_DIM = 384


def _get_model() -> Any | None:
    """Load the sentence-transformers model once; None if unavailable."""
    global _MODEL, _MODEL_FAILED
    with _LOCK:
        if _MODEL is not None or _MODEL_FAILED:
            return _MODEL
        try:
            from sentence_transformers import SentenceTransformer

            model_id = get_settings().embedding_model_id
            _MODEL = SentenceTransformer(model_id, device="cpu")
            log.info("embedding_model_loaded", model=model_id)
        except Exception as exc:  # noqa: BLE001 - memory is optional
            _MODEL_FAILED = True
            log.warning("embedding_model_unavailable", error=str(exc))
        return _MODEL


def _embed_remote(texts: list[str]) -> list[list[float]] | None:
    """Compute vectors on the inference Space; None on any failure (memory off).

    Unlike the local path there is no permanent-failure latch: remote failures
    are usually transient (Space waking, network) and recover on the next call.
    """
    from app.services.space_client import get_space_client

    try:
        data = get_space_client().post_json(
            "/embed", {"texts": texts, "normalize": True}, op="embed", retry_read_timeout=True
        )
        raw = data.get("vectors")
        if not isinstance(raw, list) or len(raw) != len(texts):
            raise ValueError("unexpected vector count")
        vectors = [[float(x) for x in vec] for vec in raw]
        if any(len(vec) != _EXPECTED_DIM for vec in vectors):
            raise ValueError("unexpected embedding dimension")
        return vectors
    except Exception as exc:  # noqa: BLE001 - memory is optional
        log.warning("embedding_remote_unavailable", error=str(exc)[:200])
        return None


def embed_texts(texts: list[str]) -> list[list[float]] | None:
    """Embed texts (BLOCKING - call via asyncio.to_thread from async code).

    Returns None when embeddings are unavailable (memory disabled).
    """
    if not texts:
        return None
    if get_settings().embeddings_mode.strip().lower() == "remote":
        return _embed_remote(texts)
    model = _get_model()
    if model is None:
        return None
    vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return [v.tolist() for v in vectors]


async def embed_texts_async(texts: list[str]) -> list[list[float]] | None:
    """Async wrapper keeping encode/model-load off the event loop."""
    if not texts:
        return None
    return await asyncio.to_thread(embed_texts, texts)


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class MemoryHit:
    source_table: str
    source_id: str
    distance: float


async def store_embedding(
    session: AsyncSession,
    *,
    source_table: str,
    source_id: str,
    text: str,
) -> bool:
    """Embed and store one text; skips duplicates (same content hash). Returns
    True when a row was written."""
    if not get_settings().enable_agent_memory:
        return False
    vectors = await embed_texts_async([text])
    if vectors is None:
        return False
    digest = content_hash(text)
    existing = await session.execute(
        select(AgentEmbedding.id).where(
            AgentEmbedding.source_table == source_table,
            AgentEmbedding.source_id == source_id,
            AgentEmbedding.content_hash == digest,
        )
    )
    if existing.scalar_one_or_none() is not None:
        return False
    session.add(
        AgentEmbedding(
            id=uuid.uuid4(),
            source_table=source_table,
            source_id=source_id,
            content_hash=digest,
            embedding=vectors[0],
        )
    )
    await session.commit()
    return True


async def search_memory(
    session: AsyncSession,
    query_text: str,
    *,
    source_table: str | None = None,
    symbol: str | None = None,
    top_k: int | None = None,
) -> list[MemoryHit]:
    """Cosine-distance search over stored embeddings; [] when memory is off.

    When ``symbol`` is given, results are restricted to agent messages
    belonging to that instrument's runs (audit LOW-2: no cross-symbol
    contamination).
    """
    settings = get_settings()
    if not settings.enable_agent_memory:
        return []
    vectors = await embed_texts_async([query_text])
    if vectors is None:
        return []
    top_k = top_k or settings.agent_memory_top_k

    distance = AgentEmbedding.embedding.cosine_distance(vectors[0])
    stmt = select(
        AgentEmbedding.source_table, AgentEmbedding.source_id, distance.label("distance")
    )
    if source_table:
        stmt = stmt.where(AgentEmbedding.source_table == source_table)
    if symbol:
        # Restrict to embeddings whose source message belongs to this symbol.
        symbol_msg_ids = (
            select(cast(AgentMessage.id, String))
            .join(AgentRun, AgentRun.id == AgentMessage.run_id)
            .where(AgentRun.symbol == symbol)
        )
        stmt = stmt.where(
            AgentEmbedding.source_table == "agent_messages",
            AgentEmbedding.source_id.in_(symbol_msg_ids),
        )
    stmt = stmt.order_by(distance).limit(top_k)

    result = await session.execute(stmt)
    return [
        MemoryHit(
            source_table=row.source_table,
            source_id=row.source_id,
            distance=float(row.distance),
        )
        for row in result
    ]


async def recall_message_notes(
    session: AsyncSession,
    query_text: str,
    *,
    symbol: str | None = None,
    top_k: int | None = None,
) -> list[str]:
    """Search memory and resolve hits into '[date] agent: snippet' note lines.

    Shared by the agent orchestrator (symbol-scoped) and the chat service
    (universe-wide). Never raises - memory is best-effort.
    """
    try:
        hits = await search_memory(session, query_text, symbol=symbol, top_k=top_k)
    except Exception as exc:  # noqa: BLE001 - memory must never break callers
        log.warning("memory_search_failed", error=str(exc))
        return []
    ids: list[uuid.UUID] = []
    for h in hits:
        if h.source_table != "agent_messages":
            continue
        try:
            ids.append(uuid.UUID(h.source_id))
        except ValueError:
            log.warning("memory_bad_source_id", source_id=h.source_id[:64])
    if not ids:
        return []
    result = await session.execute(select(AgentMessage).where(AgentMessage.id.in_(ids)))
    notes = []
    for msg in result.scalars():
        day = msg.created_at.date().isoformat() if msg.created_at else "?"
        notes.append(f"[{day}] {msg.agent_name}: {msg.content[:300]}")
    return notes


async def purge_expired_embeddings(session: AsyncSession) -> int:
    """Delete embeddings older than the configured TTL. Returns rows removed."""
    ttl_days = get_settings().memory_ttl_days
    if ttl_days <= 0:
        return 0
    cutoff = datetime.now(UTC) - timedelta(days=ttl_days)
    result = await session.execute(
        delete(AgentEmbedding).where(AgentEmbedding.created_at < cutoff)
    )
    await session.commit()
    removed = getattr(result, "rowcount", 0) or 0
    if removed:
        log.info("memory_purged", removed=removed, ttl_days=ttl_days)
    return removed
