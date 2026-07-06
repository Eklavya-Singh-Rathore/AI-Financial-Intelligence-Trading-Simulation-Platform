"""Semantic memory: local sentence-transformers embeddings + pgvector search.

Uses ``all-MiniLM-L6-v2`` (384 dims - matches the pre-existing
``agent_embeddings.embedding vector(384)`` column). The model loads lazily on
first use (~80 MB download once, cached by HF). All failures degrade to
"memory off" behaviour: agents run fine without memory.
"""

from __future__ import annotations

import hashlib
import threading
import uuid
from dataclasses import dataclass
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.agent_run import AgentEmbedding

log = structlog.get_logger(__name__)

_LOCK = threading.Lock()
_MODEL: Any | None = None
_MODEL_FAILED = False


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


def embed_texts(texts: list[str]) -> list[list[float]] | None:
    """Embed texts; None when the model is unavailable (memory disabled)."""
    if not texts:
        return None
    model = _get_model()
    if model is None:
        return None
    vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return [v.tolist() for v in vectors]


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
    vectors = embed_texts([text])
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
    top_k: int | None = None,
) -> list[MemoryHit]:
    """Cosine-distance search over stored embeddings; [] when memory is off."""
    settings = get_settings()
    if not settings.enable_agent_memory:
        return []
    vectors = embed_texts([query_text])
    if vectors is None:
        return []
    top_k = top_k or settings.agent_memory_top_k

    distance = AgentEmbedding.embedding.cosine_distance(vectors[0])
    stmt = select(
        AgentEmbedding.source_table, AgentEmbedding.source_id, distance.label("distance")
    )
    if source_table:
        stmt = stmt.where(AgentEmbedding.source_table == source_table)
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
