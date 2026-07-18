"""Finnhub provider (Phase 6): company news + quotes.

Free tier is 60 req/min (fine). Coverage of NSE symbols is partial; per-symbol
failures degrade to empty. Key travels in the ``X-Finnhub-Token`` header.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import structlog

from app.core.config import get_settings
from app.providers.base import BaseProvider, Capability, NewsItem, Quote

log = structlog.get_logger(__name__)

_BASE = "https://finnhub.io/api/v1"


class FinnhubProvider(BaseProvider):
    code = "finnhub"
    capabilities: frozenset[Capability] = frozenset({"news", "quotes"})

    def available(self) -> bool:
        return bool(get_settings().finnhub_api_key)

    def _headers(self) -> dict[str, str]:
        return {"X-Finnhub-Token": get_settings().finnhub_api_key or ""}

    def fetch_news(
        self, query: str, *, symbol: str | None = None, limit: int | None = None
    ) -> list[NewsItem]:
        # Finnhub company-news is keyed by ticker, not free text. Prefer the
        # explicit symbol hint; else treat a space-free query as a symbol.
        sym = (symbol or query).strip().strip('"')
        if not sym or " " in sym:
            return []
        to = datetime.now(UTC).date()
        frm = to - timedelta(days=get_settings().news_lookback_days)
        try:
            resp = httpx.get(
                f"{_BASE}/company-news",
                params={"symbol": sym, "from": frm.isoformat(), "to": to.isoformat()},
                headers=self._headers(),
                timeout=15.0,
            )
            if resp.status_code != 200:
                log.warning("finnhub_news_http", status=resp.status_code)
                return []
            articles = resp.json() or []
        except Exception as exc:  # noqa: BLE001 - best-effort
            log.warning("finnhub_news_failed", error=str(exc)[:200])
            return []

        cap = limit or get_settings().news_max_headlines
        out: list[NewsItem] = []
        for a in articles[:cap]:
            title = (a.get("headline") or "").strip()
            if not title:
                continue
            ts = a.get("datetime")
            published = (
                datetime.fromtimestamp(ts, tz=UTC).isoformat() if ts else ""
            )
            out.append(
                NewsItem(
                    title=title,
                    source=a.get("source") or "Finnhub",
                    published_at=published,
                    description=(a.get("summary") or "").strip()[:300],
                    url=a.get("url") or "",
                    source_provider=self.code,
                )
            )
        return out

    def get_quote(self, provider_symbol: str) -> Quote | None:
        try:
            resp = httpx.get(
                f"{_BASE}/quote",
                params={"symbol": provider_symbol},
                headers=self._headers(),
                timeout=15.0,
            )
            if resp.status_code != 200:
                return None
            d = resp.json() or {}
            price = d.get("c")
            if not price:
                return None
            return Quote(
                symbol=provider_symbol,
                price=float(price),
                change_pct=float(d["dp"]) if d.get("dp") is not None else None,
                currency=None,
                as_of=None,
                source=self.code,
            )
        except Exception as exc:  # noqa: BLE001 - best-effort
            log.warning("finnhub_quote_failed", symbol=provider_symbol, error=str(exc)[:200])
            return None
