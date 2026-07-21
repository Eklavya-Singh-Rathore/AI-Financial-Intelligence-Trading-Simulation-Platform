"""Provider abstraction tests (Phase 6): parsing, availability, registry, caps.

No live network - httpx is monkeypatched with canned responses.
"""

from __future__ import annotations

import httpx
import pytest
from app.providers import alpha_vantage, registry
from app.providers.finnhub import FinnhubProvider
from app.providers.yfinance_provider import YFinanceProvider


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    registry.reset_providers()
    yield
    registry.reset_providers()


def _mock_get(monkeypatch, module, handler):
    def fake_get(url, **kwargs):
        return handler(url, kwargs)

    monkeypatch.setattr(module.httpx, "get", fake_get)


# --- yfinance search ----------------------------------------------------------


def test_yfinance_search_parses_quotes(monkeypatch):
    payload = {
        "quotes": [
            {
                "symbol": "TCS.NS",
                "longname": "Tata Consultancy",
                "exchange": "NSI",
                "quoteType": "EQUITY",
            },
            {"symbol": "AAPL", "shortname": "Apple Inc", "exchange": "NMS", "quoteType": "EQUITY"},
            {"symbol": None},  # skipped
        ]
    }
    from app.providers import yfinance_provider

    _mock_get(monkeypatch, yfinance_provider, lambda u, k: httpx.Response(200, json=payload))
    matches = YFinanceProvider().search_symbols("tata", limit=10)
    assert [m.provider_symbol for m in matches] == ["TCS.NS", "AAPL"]
    assert matches[0].exchange == "NSE"  # NSI -> NSE
    assert matches[0].name == "Tata Consultancy"


def test_yfinance_search_degrades_on_error(monkeypatch):
    from app.providers import yfinance_provider

    def boom(u, k):
        raise httpx.ConnectError("no net")

    _mock_get(monkeypatch, yfinance_provider, boom)
    assert YFinanceProvider().search_symbols("x") == []


# --- finnhub ------------------------------------------------------------------


def test_finnhub_unavailable_without_key(monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setenv("FINNHUB_API_KEY", "")
    get_settings.cache_clear()
    try:
        assert FinnhubProvider().available() is False
    finally:
        get_settings.cache_clear()


def test_finnhub_news_parses(monkeypatch):
    from app.core.config import get_settings
    from app.providers import finnhub

    monkeypatch.setenv("FINNHUB_API_KEY", "k")
    get_settings.cache_clear()
    payload = [
        {
            "headline": "Big deal",
            "source": "Reuters",
            "datetime": 1_700_000_000,
            "summary": "details",
            "url": "https://x/1",
        },
        {"headline": "", "datetime": 1},  # skipped (no title)
    ]
    _mock_get(monkeypatch, finnhub, lambda u, k: httpx.Response(200, json=payload))
    try:
        items = FinnhubProvider().fetch_news("TCS")
        assert len(items) == 1
        assert items[0].title == "Big deal"
        assert items[0].source_provider == "finnhub"
    finally:
        get_settings.cache_clear()


def test_finnhub_news_skips_free_text(monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setenv("FINNHUB_API_KEY", "k")
    get_settings.cache_clear()
    try:
        # A quoted display name (has spaces) isn't a symbol -> [].
        assert FinnhubProvider().fetch_news('"Tata Consultancy Services"') == []
    finally:
        get_settings.cache_clear()


# --- alpha vantage daily cap --------------------------------------------------


def test_alpha_vantage_daily_cap(monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "k")
    monkeypatch.setenv("ALPHA_VANTAGE_DAILY_CAP", "2")
    get_settings.cache_clear()
    # Reset the module counter.
    alpha_vantage._day = None
    alpha_vantage._calls_today = 0
    _mock_get(
        monkeypatch,
        alpha_vantage,
        lambda u, k: httpx.Response(200, json={"Symbol": "X", "Name": "X Corp"}),
    )
    try:
        prov = alpha_vantage.AlphaVantageProvider()
        assert prov.fetch_fundamentals("X") is not None
        assert prov.fetch_fundamentals("X") is not None
        # Third call exceeds the cap of 2 -> None without a request.
        assert prov.fetch_fundamentals("X") is None
    finally:
        get_settings.cache_clear()


# --- registry aggregates ------------------------------------------------------


def test_registry_news_merges_and_dedupes(monkeypatch):
    from app.providers.base import BaseProvider, NewsItem

    class A(BaseProvider):
        code = "a"
        capabilities = frozenset({"news"})

        def fetch_news(self, query, *, symbol=None, limit=None):
            return [
                NewsItem("Same", "s", "2026", url="u1"),
                NewsItem("Only A", "s", "2026", url="u2"),
            ]

    class B(BaseProvider):
        code = "b"
        capabilities = frozenset({"news"})

        def fetch_news(self, query, *, symbol=None, limit=None):
            return [
                NewsItem("Same", "s", "2026", url="u1"),
                NewsItem("Only B", "s", "2026", url="u3"),
            ]

    monkeypatch.setattr(registry, "_PROVIDERS", {"a": A(), "b": B()})
    monkeypatch.setenv("PROVIDER_PRIORITY", "a,b")
    from app.core.config import get_settings

    get_settings.cache_clear()
    try:
        titles = [n.title for n in registry.fetch_news("q")]
        assert titles == ["Same", "Only A", "Only B"]  # deduped, priority order
    finally:
        get_settings.cache_clear()


def test_yfinance_news_parses(monkeypatch):
    from app.providers import yfinance_provider

    payload = {
        "news": [
            {
                "title": "Reliance jumps",
                "publisher": "Mint",
                "link": "https://x/1",
                "providerPublishTime": 1_700_000_000,
            },
            {"title": "", "link": "https://x/2"},  # skipped (no title)
        ]
    }
    _mock_get(monkeypatch, yfinance_provider, lambda u, k: httpx.Response(200, json=payload))
    items = YFinanceProvider().fetch_news('"Reliance Industries"')
    assert len(items) == 1
    assert items[0].title == "Reliance jumps"
    assert items[0].source == "Mint"
    assert items[0].url == "https://x/1"
    assert items[0].source_provider == "yfinance"


def test_alpha_vantage_news_parses_and_needs_symbol(monkeypatch):
    from app.core.config import get_settings
    from app.providers import alpha_vantage as av

    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "k")
    monkeypatch.setenv("ALPHA_VANTAGE_DAILY_CAP", "5")
    get_settings.cache_clear()
    av._day = None
    av._calls_today = 0
    payload = {
        "feed": [
            {
                "title": "AV story",
                "source": "Zacks",
                "url": "https://x/av",
                "time_published": "20260721T143000",
                "summary": "sum",
            },
            {"title": "", "url": "y"},  # skipped
        ]
    }
    _mock_get(monkeypatch, av, lambda u, k: httpx.Response(200, json=payload))
    try:
        items = av.AlphaVantageProvider().fetch_news("ignored", symbol="AAPL")
        assert len(items) == 1
        assert items[0].title == "AV story"
        assert items[0].published_at.startswith("2026-07-21T14:30:00")
        assert items[0].source_provider == "alpha_vantage"
        # No ticker -> skip entirely (AV can't free-text search), no call spent.
        assert av.AlphaVantageProvider().fetch_news("some name") == []
    finally:
        get_settings.cache_clear()


def test_rank_and_merge_overlap_and_ranking():
    from datetime import UTC, datetime

    from app.providers.base import NewsItem
    from app.providers.registry import rank_and_merge_news

    now = datetime(2026, 7, 21, tzinfo=UTC)
    items = [
        # Same story from two providers (different URL, different case) -> merged.
        NewsItem(
            "Reliance Q1 profit rises",
            "Mint",
            "2026-07-20T10:00:00+00:00",
            url="u1",
            source_provider="newsapi",
        ),
        NewsItem(
            "RELIANCE Q1 PROFIT RISES",
            "Reuters",
            "2026-07-20T09:00:00+00:00",
            description="longer detail",
            url="u2",
            source_provider="finnhub",
        ),
        NewsItem(
            "Market wrap", "PTI", "2026-07-14T10:00:00+00:00", url="u3", source_provider="yahoo"
        ),
    ]
    out = rank_and_merge_news(
        items, query='"Reliance"', symbol="RELIANCE", limit=10, lookback_days=7, now=now
    )
    assert len(out) == 2  # the two Reliance items collapsed into one
    assert "reliance" in out[0].title.lower()
    assert out[0].description == "longer detail"  # richer copy kept
    assert set(out[0].source_provider.split("+")) == {"newsapi", "finnhub"}  # attribution
    assert out[1].title == "Market wrap"  # less relevant + older ranks last


def test_registry_search_falls_through_unavailable(monkeypatch):
    from app.providers.base import BaseProvider, SymbolMatch

    class Off(BaseProvider):
        code = "off"
        capabilities = frozenset({"symbol_search"})

        def available(self):
            return False

        def search_symbols(self, query, *, limit=10):
            raise AssertionError("must not be called")

    class On(BaseProvider):
        code = "on"
        capabilities = frozenset({"symbol_search"})

        def search_symbols(self, query, *, limit=10):
            return [SymbolMatch("SYM", "Name", source="on")]

    monkeypatch.setattr(registry, "_PROVIDERS", {"off": Off(), "on": On()})
    monkeypatch.setenv("PROVIDER_PRIORITY", "off,on")
    from app.core.config import get_settings

    get_settings.cache_clear()
    try:
        assert registry.search_symbols("q")[0].provider_symbol == "SYM"
    finally:
        get_settings.cache_clear()
