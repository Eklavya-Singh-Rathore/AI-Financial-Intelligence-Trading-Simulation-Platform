"""Tests for the embeddings/memory service."""

from __future__ import annotations

import pytest
from app.core.config import Settings
from app.services import embeddings
from app.services.embeddings import content_hash, embed_texts
from app.services.space_client import SpaceClientError


def test_content_hash_stable_and_distinct():
    assert content_hash("abc") == content_hash("abc")
    assert content_hash("abc") != content_hash("abd")
    assert len(content_hash("abc")) == 64


def test_embed_empty_list_returns_none():
    assert embed_texts([]) is None


class _StubSpaceClient:
    def __init__(self, response: dict | None = None, error: Exception | None = None):
        self.response = response
        self.error = error
        self.calls: list[dict] = []

    def post_json(self, path: str, payload: dict, *, op: str, retry_read_timeout: bool = False):
        assert path == "/embed"
        assert op == "embed"
        assert retry_read_timeout is True  # embed calls are cheap - retry them
        self.calls.append(payload)
        if self.error is not None:
            raise self.error
        return self.response


def _remote_mode(monkeypatch, stub: _StubSpaceClient) -> None:
    monkeypatch.setattr(
        embeddings, "get_settings", lambda: Settings(_env_file=None, embeddings_mode="remote")
    )
    monkeypatch.setattr("app.services.space_client.get_space_client", lambda: stub)


def test_embed_texts_remote_mode(monkeypatch):
    stub = _StubSpaceClient(
        response={"vectors": [[0.1] * 384, [0.2] * 384], "dim": 384}
    )
    _remote_mode(monkeypatch, stub)
    vectors = embed_texts(["hello market", "prices rising"])
    assert vectors is not None
    assert len(vectors) == 2
    assert all(len(v) == 384 for v in vectors)
    assert stub.calls == [{"texts": ["hello market", "prices rising"], "normalize": True}]


def test_embed_texts_remote_failure_degrades_to_none(monkeypatch):
    stub = _StubSpaceClient(error=SpaceClientError("inference service timed out", kind="timeout"))
    _remote_mode(monkeypatch, stub)
    assert embed_texts(["hello"]) is None  # memory off, never raises


def test_embed_texts_remote_wrong_dim_degrades_to_none(monkeypatch):
    stub = _StubSpaceClient(response={"vectors": [[0.1] * 10]})
    _remote_mode(monkeypatch, stub)
    assert embed_texts(["hello"]) is None


def test_embed_texts_remote_wrong_count_degrades_to_none(monkeypatch):
    stub = _StubSpaceClient(response={"vectors": [[0.1] * 384]})
    _remote_mode(monkeypatch, stub)
    assert embed_texts(["a", "b"]) is None


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
