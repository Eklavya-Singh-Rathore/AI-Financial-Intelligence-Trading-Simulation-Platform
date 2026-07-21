"""Provider registry + aggregate helpers (Phase 6).

Lazily builds the configured providers, orders them by ``PROVIDER_PRIORITY``,
and exposes capability-scoped aggregates that never raise. OpenBB is
deliberately NOT registered (too heavy for the 512 MB slim image); a slot is
reserved in the priority string for a future remote deployment.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

import structlog

from app.core.config import get_settings
from app.providers.base import BaseProvider, Capability, NewsItem, SymbolMatch

log = structlog.get_logger(__name__)


def _norm_title(title: str) -> str:
    """Lowercased, alphanumeric-only, whitespace-collapsed title (dedup key)."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", "", (title or "").lower())).strip()


def _tokens(text: str) -> set[str]:
    return {w for w in _norm_title(text).split() if len(w) > 2}


def _age_days(published_at: str, now: datetime) -> float | None:
    if not published_at:
        return None
    try:
        dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return max(0.0, (now - dt).total_seconds() / 86400.0)


def rank_and_merge_news(
    items: list[NewsItem],
    *,
    query: str = "",
    symbol: str | None = None,
    limit: int | None = None,
    lookback_days: int = 7,
    now: datetime | None = None,
) -> list[NewsItem]:
    """Merge overlapping stories and rank by relevance + recency (pure).

    Stories are grouped by normalized title (so the same headline from several
    providers collapses to one), keeping the richest copy and recording every
    contributing API in ``source_provider`` (e.g. "newsapi+finnhub"); the
    publisher (``source``) attribution is preserved untouched. Ranking favors
    query/symbol token overlap, then recency within the look-back window.
    """
    now = now or datetime.now(UTC)
    q_tokens = _tokens(query)
    if symbol:
        q_tokens.add(symbol.strip().lower())

    best: dict[str, NewsItem] = {}
    provs: dict[str, list[str]] = {}
    for it in items:
        key = _norm_title(it.title)
        if not key:
            continue
        cur = best.get(key)
        if cur is None or len(it.description) > len(cur.description):
            best[key] = it
        contributors = provs.setdefault(key, [])
        if it.source_provider and it.source_provider not in contributors:
            contributors.append(it.source_provider)

    def score(it: NewsItem) -> tuple[float, str]:
        toks = _tokens(f"{it.title} {it.description}")
        relevance = len(q_tokens & toks) / len(q_tokens) if q_tokens else 0.0
        age = _age_days(it.published_at, now)
        recency = max(0.0, 1.0 - age / lookback_days) if age is not None else 0.0
        return (relevance * 2.0 + recency, it.published_at)

    merged = [
        NewsItem(
            title=it.title,
            source=it.source,
            published_at=it.published_at,
            description=it.description,
            url=it.url,
            source_provider="+".join(provs.get(key, [])) or it.source_provider,
        )
        for key, it in best.items()
    ]
    merged.sort(key=score, reverse=True)
    return merged[:limit] if limit else merged


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


def fetch_news(
    query: str, *, symbol: str | None = None, limit: int | None = None
) -> list[NewsItem]:
    """Consolidated news across every available news provider.

    ``query`` is free text (NewsAPI/Yahoo); ``symbol`` is the provider ticker
    for symbol-keyed sources (Finnhub/Alpha Vantage). Each provider is fetched
    best-effort, then overlapping stories are merged and ranked by relevance +
    recency (see ``rank_and_merge_news``).
    """
    collected: list[NewsItem] = []
    for provider in providers_for("news"):
        try:
            collected.extend(provider.fetch_news(query, symbol=symbol, limit=limit))
        except Exception as exc:  # noqa: BLE001 - one provider must not sink the rest
            log.warning("news_provider_failed", provider=provider.code, error=str(exc)[:200])
    return rank_and_merge_news(
        collected,
        query=query,
        symbol=symbol,
        limit=limit,
        lookback_days=get_settings().news_lookback_days,
    )
