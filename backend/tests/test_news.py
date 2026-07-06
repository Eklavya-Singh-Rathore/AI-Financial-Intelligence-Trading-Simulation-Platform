"""Unit tests for the news service (pure parsing; no network)."""

from __future__ import annotations

from app.services.news import Headline, parse_articles

PAYLOAD = {
    "status": "ok",
    "articles": [
        {
            "title": "Reliance posts record quarterly profit",
            "source": {"name": "Business Standard"},
            "publishedAt": "2026-07-05T09:30:00Z",
            "description": "Q1 results beat estimates on retail strength.",
            "url": "https://example.com/1",
        },
        {
            "title": "[Removed]",
            "source": {"name": "x"},
            "publishedAt": "2026-07-05T00:00:00Z",
        },
        {
            "title": "Analysts split on energy outlook",
            "source": {},
            "publishedAt": "2026-07-04T12:00:00Z",
            "description": None,
        },
        {"title": "", "source": {"name": "y"}, "publishedAt": ""},
        {
            "title": "Fourth valid article beyond limit",
            "source": {"name": "z"},
            "publishedAt": "2026-07-03T00:00:00Z",
        },
    ],
}


def test_parse_articles_filters_and_limits():
    # limit applies to raw article slots (5 given, take 4 -> 2 valid survive filters)
    headlines = parse_articles(PAYLOAD, limit=4)
    assert [h.title for h in headlines] == [
        "Reliance posts record quarterly profit",
        "Analysts split on energy outlook",
    ]
    assert headlines[0].source == "Business Standard"
    assert headlines[1].source == "unknown"
    assert headlines[1].description == ""


def test_parse_articles_empty_payload():
    assert parse_articles({}, limit=10) == []
    assert parse_articles({"articles": None}, limit=10) == []


def test_headline_prompt_line():
    h = Headline(
        title="T", source="S", published_at="2026-07-05T09:30:00Z", description="D"
    )
    assert h.as_prompt_line() == "[2026-07-05] (S) T - D"
    h2 = Headline(title="T", source="S", published_at="2026-07-05T09:30:00Z")
    assert h2.as_prompt_line() == "[2026-07-05] (S) T"
