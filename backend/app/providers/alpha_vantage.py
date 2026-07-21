"""Alpha Vantage provider (Phase 6): fundamentals + quotes.

Free tier is a HARD 25 requests/day, so a process-level daily counter refuses
calls beyond ``ALPHA_VANTAGE_DAILY_CAP`` (default 20) to leave headroom. NSE
coverage is weak (better for US symbols / ``.BSE`` suffix); positioned as a
supplemental fundamentals source behind yfinance.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime

import httpx
import structlog

from app.core.config import get_settings
from app.providers.base import BaseProvider, Capability, FundamentalsBundle, NewsItem, Quote

log = structlog.get_logger(__name__)

_BASE = "https://www.alphavantage.co/query"


def _av_time(raw: str | None) -> str:
    """AV ``time_published`` ("YYYYMMDDTHHMMSS") -> ISO; "" on any failure."""
    if not raw:
        return ""
    try:
        return datetime.strptime(raw, "%Y%m%dT%H%M%S").replace(tzinfo=UTC).isoformat()
    except (ValueError, TypeError):
        return ""


_lock = threading.Lock()
_day: str | None = None
_calls_today = 0


def _reserve_call() -> bool:
    """Reserve one call against today's cap; False when exhausted."""
    global _day, _calls_today
    today = datetime.now(UTC).date().isoformat()
    with _lock:
        if _day != today:
            _day = today
            _calls_today = 0
        if _calls_today >= get_settings().alpha_vantage_daily_cap:
            return False
        _calls_today += 1
        return True


class AlphaVantageProvider(BaseProvider):
    code = "alpha_vantage"
    capabilities: frozenset[Capability] = frozenset({"fundamentals", "quotes", "news"})

    def available(self) -> bool:
        return bool(get_settings().alpha_vantage_api_key)

    def fetch_news(
        self, query: str, *, symbol: str | None = None, limit: int | None = None
    ) -> list[NewsItem]:
        """AV NEWS_SENTIMENT is ticker-keyed (no free-text name search), so it
        contributes only when a provider ticker is supplied. Shares the hard
        daily cap with fundamentals/quotes, so it degrades to [] once exhausted."""
        sym = (symbol or "").strip()
        if not sym:
            return []
        cap = limit or get_settings().news_max_headlines
        data = self._get(
            {"function": "NEWS_SENTIMENT", "tickers": sym, "sort": "LATEST", "limit": min(cap, 50)}
        )
        feed = (data or {}).get("feed") or []
        out: list[NewsItem] = []
        for a in feed[:cap]:
            title = (a.get("title") or "").strip()
            if not title:
                continue
            out.append(
                NewsItem(
                    title=title,
                    source=a.get("source") or "Alpha Vantage",
                    published_at=_av_time(a.get("time_published")),
                    description=(a.get("summary") or "").strip()[:300],
                    url=a.get("url") or "",
                    source_provider=self.code,
                )
            )
        return out

    def _get(self, params: dict) -> dict | None:
        if not _reserve_call():
            log.warning("alpha_vantage_daily_cap_reached")
            return None
        params = {**params, "apikey": get_settings().alpha_vantage_api_key}
        try:
            resp = httpx.get(_BASE, params=params, timeout=20.0)
            if resp.status_code != 200:
                return None
            data = resp.json()
            # AV returns {"Note": ...} or {"Information": ...} on throttle.
            if not isinstance(data, dict) or "Note" in data or "Information" in data:
                return None
            return data
        except Exception as exc:  # noqa: BLE001 - best-effort
            log.warning("alpha_vantage_failed", error=str(exc)[:200])
            return None

    def fetch_fundamentals(self, provider_symbol: str) -> FundamentalsBundle | None:
        data = self._get({"function": "OVERVIEW", "symbol": provider_symbol})
        if not data or not data.get("Symbol"):
            return None
        return FundamentalsBundle(data=data, as_of=datetime.now(UTC).isoformat(), source=self.code)

    def get_quote(self, provider_symbol: str) -> Quote | None:
        data = self._get({"function": "GLOBAL_QUOTE", "symbol": provider_symbol})
        gq = (data or {}).get("Global Quote") or {}
        price = gq.get("05. price")
        if not price:
            return None
        change_pct = (gq.get("10. change percent") or "").rstrip("%") or None
        try:
            return Quote(
                symbol=provider_symbol,
                price=float(price),
                change_pct=float(change_pct) if change_pct else None,
                currency=None,
                as_of=gq.get("07. latest trading day"),
                source=self.code,
            )
        except (TypeError, ValueError):
            return None
