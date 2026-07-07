"""News headlines via NewsAPI.org (for the news/sentiment analyst).

Degrades gracefully: with no key, on HTTP errors, or when the free-tier quota is
hit, it returns an empty list and logs a warning - agent runs proceed without
news rather than failing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
import structlog

from app.core.config import get_settings

log = structlog.get_logger(__name__)

NEWSAPI_URL = "https://newsapi.org/v2/everything"


@dataclass
class Headline:
    title: str
    source: str
    published_at: str  # ISO date-time string
    description: str = ""
    url: str = ""

    def as_prompt_line(self) -> str:
        date = self.published_at[:10]
        desc = f" - {self.description}" if self.description else ""
        return f"[{date}] ({self.source}) {self.title}{desc}"


def parse_articles(payload: dict, limit: int) -> list[Headline]:
    """Convert a NewsAPI response payload into Headlines (pure function)."""
    articles = payload.get("articles") or []
    headlines: list[Headline] = []
    for art in articles[:limit]:
        title = (art.get("title") or "").strip()
        if not title or title == "[Removed]":
            continue
        headlines.append(
            Headline(
                title=title,
                source=((art.get("source") or {}).get("name") or "unknown"),
                published_at=art.get("publishedAt") or "",
                description=(art.get("description") or "").strip()[:300],
                url=art.get("url") or "",
            )
        )
    return headlines


def fetch_headlines(
    query: str, *, days: int | None = None, limit: int | None = None
) -> list[Headline]:
    """Fetch recent English headlines matching ``query`` (synchronous; wrap in
    ``asyncio.to_thread`` from async code)."""
    settings = get_settings()
    if not settings.newsapi_key:
        log.warning("newsapi_key_missing")
        return []
    days = days if days is not None else settings.news_lookback_days
    limit = limit if limit is not None else settings.news_max_headlines
    from_date = (datetime.now(UTC) - timedelta(days=days)).date().isoformat()

    params: dict[str, str | int] = {
        "q": query,
        "from": from_date,
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": min(limit, 100),
    }
    try:
        # Key travels in a header, not the query string, so proxies/access logs
        # never see it (audit LOW-1).
        response = httpx.get(
            NEWSAPI_URL,
            params=params,
            headers={"X-Api-Key": settings.newsapi_key},
            timeout=20.0,
        )
        payload = response.json()
        if response.status_code != 200 or payload.get("status") != "ok":
            log.warning(
                "newsapi_error",
                status_code=response.status_code,
                api_code=payload.get("code"),
                message=str(payload.get("message"))[:200],
            )
            return []
        headlines = parse_articles(payload, limit)
        log.info("newsapi_fetched", query=query, count=len(headlines))
        return headlines
    except Exception as exc:  # noqa: BLE001 - news is best-effort
        log.warning("newsapi_request_failed", query=query, error=str(exc))
        return []
