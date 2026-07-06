"""Tests for the embeddings/memory service."""

from __future__ import annotations

import pytest
from app.services.embeddings import content_hash, embed_texts


def test_content_hash_stable_and_distinct():
    assert content_hash("abc") == content_hash("abc")
    assert content_hash("abc") != content_hash("abd")
    assert len(content_hash("abc")) == 64


def test_embed_empty_list_returns_none():
    assert embed_texts([]) is None


@pytest.mark.slow
def test_minilm_dimensions_match_table():
    """Loads the real MiniLM model (downloads once) - must produce 384 dims."""
    vectors = embed_texts(["hello market", "prices rising"])
    if vectors is None:
        pytest.skip("embedding model unavailable in this environment")
    assert len(vectors) == 2
    assert len(vectors[0]) == 384
    # normalized embeddings -> unit-ish norm
    norm = sum(v * v for v in vectors[0]) ** 0.5
    assert norm == pytest.approx(1.0, abs=1e-3)
