"""Provider registry + aggregate helpers (Phase 6).

Lazily builds the configured providers, orders them by ``PROVIDER_PRIORITY``,
and exposes capability-scoped aggregates that never raise. OpenBB is
deliberately NOT registered (too heavy for the 512 MB slim image); a slot is
reserved in the priority string for a future remote deployment.
"""

from __future__ import annotations

import structlog

from app.core.config import get_settings
from app.providers.base import BaseProvider, Capability, NewsItem, SymbolMatch

log = structlog.get_logger(__name__)

_PROVIDERS: dict[str, BaseProvider] | None = None


def _build() -> dict[str, BaseProvider]:
    from app.providers.alpha_vantage import AlphaVantageProvider
    from app.providers.finnhub import FinnhubProvider
    from app.providers.newsapi_provider import NewsAPIProvider
    from app.providers.yfinance_provider import YFinanceProvider

    providers: list[BaseProvider] = [
        YFinanceProvider(),
        FinnhubProvider(),
        AlphaVantageProvider(),
        NewsAPIProvider(),
    ]
    return {p.code: p for p in providers}


def _all() -> dict[str, BaseProvider]:
    global _PROVIDERS
    if _PROVIDERS is None:
        _PROVIDERS = _build()
    return _PROVIDERS


def reset_providers() -> None:
    """Drop the cached providers (tests / settings reloads)."""
    global _PROVIDERS
    _PROVIDERS = None


def _priority_order() -> list[str]:
    return [c.strip() for c in get_settings().provider_priority.split(",") if c.strip()]


def providers_for(capability: Capability) -> list[BaseProvider]:
    """Available providers supporting ``capability``, in priority order."""
    registry = _all()
    ordered = _priority_order()
    ranked = sorted(
        (p for p in registry.values() if p.has(capability) and p.available()),
        key=lambda p: ordered.index(p.code) if p.code in ordered else len(ordered),
    )
    return ranked


def search_symbols(query: str, *, limit: int = 10) -> list[SymbolMatch]:
    """First available symbol-search provider; [] if none/failure."""
    for provider in providers_for("symbol_search"):
        results = provider.search_symbols(query, limit=limit)
        if results:
            return results
    return []


def fetch_news(query: str, *, limit: int | None = None) -> list[NewsItem]:
    """Merge news across all available news providers, deduped by title|url."""
    seen: set[str] = set()
    merged: list[NewsItem] = []
    for provider in providers_for("news"):
        for item in provider.fetch_news(query, limit=limit):
            key = f"{item.title.strip().lower()}|{item.url}"
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
    return merged
