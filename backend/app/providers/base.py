"""Provider interface + result dataclasses (Phase 6)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Capability = Literal["quotes", "fundamentals", "news", "sentiment", "symbol_search", "ohlcv"]


@dataclass
class OhlcvBar:
    """One OHLCV bar. ``time`` is an ISO string: a date ("2026-07-17") for
    daily/weekly/monthly, or naive exchange-local wall-clock
    ("2026-07-20T09:15:00") for intraday (so the chart renders IST times)."""

    time: str
    open: float
    high: float
    low: float
    close: float
    volume: int


@dataclass
class SymbolMatch:
    provider_symbol: str
    name: str
    exchange: str | None = None
    asset_type: str | None = None
    source: str = ""


@dataclass
class Quote:
    symbol: str
    price: float | None
    change_pct: float | None
    currency: str | None
    as_of: str | None
    source: str = ""


@dataclass
class NewsItem:
    title: str
    source: str
    published_at: str  # ISO string
    description: str = ""
    url: str = ""
    source_provider: str = ""

    def as_prompt_line(self) -> str:
        """Compact line for the agent prompt (mirrors news.Headline)."""
        date = self.published_at[:10]
        desc = f" - {self.description}" if self.description else ""
        return f"[{date}] ({self.source}) {self.title}{desc}"


@dataclass
class FundamentalsBundle:
    data: dict = field(default_factory=dict)
    as_of: str | None = None
    source: str = ""


class BaseProvider:
    """A single external data source. Subclasses set ``code``/``capabilities``
    and override the capability methods they support. All methods are
    SYNCHRONOUS (callers wrap in ``asyncio.to_thread``) and must NEVER raise -
    return an empty result on any failure."""

    code: str = "base"
    capabilities: frozenset[Capability] = frozenset()

    def available(self) -> bool:
        """True when this provider is usable (keys/config present)."""
        return True

    def has(self, capability: Capability) -> bool:
        return capability in self.capabilities

    # -- capability methods (override the supported ones) -------------------
    def search_symbols(self, query: str, *, limit: int = 10) -> list[SymbolMatch]:
        return []

    def get_quote(self, provider_symbol: str) -> Quote | None:
        return None

    def fetch_news(
        self, query: str, *, symbol: str | None = None, limit: int | None = None
    ) -> list[NewsItem]:
        """Fetch news. ``query`` is free text (display name); ``symbol`` is the
        provider ticker for symbol-keyed sources (Finnhub)."""
        return []

    def fetch_fundamentals(self, provider_symbol: str) -> FundamentalsBundle | None:
        return None

    def fetch_ohlcv(
        self, provider_symbol: str, interval: str, *, period: str | None = None
    ) -> list[OhlcvBar]:
        """Fetch intraday/daily OHLCV bars at ``interval`` (e.g. '5m', '1d').
        ``period`` is a provider look-back hint. Empty list on any failure."""
        return []
