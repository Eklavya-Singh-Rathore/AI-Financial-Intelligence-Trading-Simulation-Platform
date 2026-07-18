"""NewsAPI provider (Phase 6): adapts the existing news.py client.

The 7-agent pipeline keeps importing ``app.services.news`` directly, so this
adapter is purely additive - it lets the aggregate news fetch include NewsAPI
alongside Finnhub through one interface.
"""

from __future__ import annotations

from app.core.config import get_settings
from app.providers.base import BaseProvider, Capability, NewsItem
from app.services import news


class NewsAPIProvider(BaseProvider):
    code = "newsapi"
    capabilities: frozenset[Capability] = frozenset({"news"})

    def available(self) -> bool:
        return bool(get_settings().newsapi_key)

    def fetch_news(self, query: str, *, limit: int | None = None) -> list[NewsItem]:
        headlines = news.fetch_headlines(query, limit=limit)
        return [
            NewsItem(
                title=h.title,
                source=h.source,
                published_at=h.published_at,
                description=h.description,
                url=h.url,
                source_provider=self.code,
            )
            for h in headlines
        ]
