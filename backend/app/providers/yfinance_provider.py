"""yfinance provider (Phase 6): keyless symbol search + quotes.

Search uses ``yf.Search`` when the installed version supports it, else falls
back to Yahoo's public search JSON endpoint (no key). Everything degrades to
empty on any failure.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import structlog

from app.core.config import get_settings
from app.providers.base import BaseProvider, Capability, NewsItem, Quote, SymbolMatch

log = structlog.get_logger(__name__)

_YAHOO_SEARCH = "https://query2.finance.yahoo.com/v1/finance/search"
# Yahoo exchange codes we surface as Indian listings.
_INDIA_EXCHANGES = {"NSI": "NSE", "BSE": "BSE"}


class YFinanceProvider(BaseProvider):
    code = "yfinance"
    capabilities: frozenset[Capability] = frozenset({"symbol_search", "quotes", "news"})

    def available(self) -> bool:
        return True  # keyless

    def fetch_news(
        self, query: str, *, symbol: str | None = None, limit: int | None = None
    ) -> list[NewsItem]:
        """Yahoo Finance news via the keyless search endpoint's ``news`` array
        (free-text query = display name). No summaries are provided by Yahoo."""
        q = (query or symbol or "").strip().strip('"')
        if not q:
            return []
        cap = limit or get_settings().news_max_headlines
        try:
            resp = httpx.get(
                _YAHOO_SEARCH,
                params={"q": q, "quotesCount": 0, "newsCount": min(cap, 20)},
                headers={"User-Agent": "Mozilla/5.0 (compatible; ai-fin-platform/0.1)"},
                timeout=15.0,
            )
            if resp.status_code != 200:
                log.warning("yf_news_http", status=resp.status_code)
                return []
            news = resp.json().get("news") or []
        except Exception as exc:  # noqa: BLE001 - news is best-effort
            log.warning("yf_news_failed", error=str(exc)[:200])
            return []

        out: list[NewsItem] = []
        for n in news[:cap]:
            title = (n.get("title") or "").strip()
            if not title:
                continue
            ts = n.get("providerPublishTime")
            published = datetime.fromtimestamp(ts, tz=UTC).isoformat() if ts else ""
            out.append(
                NewsItem(
                    title=title,
                    source=n.get("publisher") or "Yahoo Finance",
                    published_at=published,
                    description="",
                    url=n.get("link") or "",
                    source_provider=self.code,
                )
            )
        return out

    def search_symbols(self, query: str, *, limit: int = 10) -> list[SymbolMatch]:
        query = query.strip()
        if len(query) < 1:
            return []
        try:
            resp = httpx.get(
                _YAHOO_SEARCH,
                params={"q": query, "quotesCount": limit, "newsCount": 0},
                headers={"User-Agent": "Mozilla/5.0 (compatible; ai-fin-platform/0.1)"},
                timeout=15.0,
            )
            if resp.status_code != 200:
                log.warning("yf_search_http", status=resp.status_code)
                return []
            quotes = resp.json().get("quotes") or []
        except Exception as exc:  # noqa: BLE001 - search is best-effort
            log.warning("yf_search_failed", error=str(exc)[:200])
            return []

        out: list[SymbolMatch] = []
        for q in quotes:
            sym = q.get("symbol")
            if not sym:
                continue
            out.append(
                SymbolMatch(
                    provider_symbol=sym,
                    name=q.get("longname") or q.get("shortname") or sym,
                    exchange=_INDIA_EXCHANGES.get(q.get("exchange", ""), q.get("exchange")),
                    asset_type=(q.get("quoteType") or "").lower() or None,
                    source=self.code,
                )
            )
        return out[:limit]

    def get_quote(self, provider_symbol: str) -> Quote | None:
        try:
            import yfinance as yf

            fi = yf.Ticker(provider_symbol).fast_info
            price = getattr(fi, "last_price", None)
            prev = getattr(fi, "previous_close", None)
            change = (price / prev - 1.0) * 100.0 if price and prev else None
            return Quote(
                symbol=provider_symbol,
                price=float(price) if price is not None else None,
                change_pct=round(change, 2) if change is not None else None,
                currency=getattr(fi, "currency", None),
                as_of=None,
                source=self.code,
            )
        except Exception as exc:  # noqa: BLE001 - quotes are best-effort
            log.warning("yf_quote_failed", symbol=provider_symbol, error=str(exc)[:200])
            return None
