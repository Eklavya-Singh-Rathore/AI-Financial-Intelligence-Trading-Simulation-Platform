"""News-RAG unit tests: hashing, citation formatting, timestamp parsing.

Pure transforms only - persistence/KNN round-trips live in the db-marked
suite (test_news_rag_db.py).
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from app.services.news_rag import (
    citation_lines,
    citation_refs,
    embed_text_for,
    headline_hash,
    parse_published,
)


def test_headline_hash_stable_and_distinct():
    a = headline_hash("RBI holds rates", "https://x.test/a")
    assert a == headline_hash("RBI holds rates", "https://x.test/a")
    assert a != headline_hash("RBI holds rates", "https://x.test/b")
    assert a != headline_hash("RBI cuts rates", "https://x.test/a")
    assert len(a) == 64


def test_parse_published():
    dt = parse_published("2026-07-12T08:30:00Z")
    assert dt == datetime(2026, 7, 12, 8, 30, tzinfo=UTC)
    assert parse_published("") is None
    assert parse_published("not-a-date") is None


def test_embed_text_for():
    assert embed_text_for("Title", "Desc") == "Title. Desc"
    assert embed_text_for("Title", "") == "Title"


def _doc(title: str, content: str = "", url: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        title=title,
        content=content,
        source_url=url,
        published_at=datetime(2026, 7, 12, tzinfo=UTC),
        symbol="TCS",
    )


def test_citation_lines_numbered_and_dated():
    lines = citation_lines([_doc("First story", "detail here"), _doc("Second story")])
    assert lines[0] == "[1] [2026-07-12] First story - detail here"
    assert lines[1] == "[2] [2026-07-12] Second story"


def test_citation_refs_json_shape():
    refs = citation_refs([_doc("Story", url="https://x.test/a")])
    assert refs == [
        {
            "n": 1,
            "title": "Story",
            "url": "https://x.test/a",
            "published_at": "2026-07-12T00:00:00+00:00",
            "symbol": "TCS",
        }
    ]
