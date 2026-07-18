"""Curated-catalog validation + news quota selector (pure, no DB/network)."""

from __future__ import annotations

from app.catalog.curated import CURATED_UNIVERSE
from app.services.news_rag import select_news_symbols

ORIGINAL_16 = {
    "ASIANPAINT", "BHARTIARTL", "GOLD", "HDFCBANK", "HINDUNILVR", "ICICIBANK",
    "INFY", "ITC", "LT", "NIFTY50", "RELIANCE", "SBIN", "SENSEX", "SILVER",
    "TATAMOTORS", "TCS",
}


def test_catalog_size_and_originals_present():
    symbols = {e.symbol for e in CURATED_UNIVERSE}
    assert len(CURATED_UNIVERSE) >= 100
    assert symbols >= ORIGINAL_16


def test_catalog_symbols_unique():
    symbols = [e.symbol for e in CURATED_UNIVERSE]
    assert len(symbols) == len(set(symbols))
    provider_symbols = [e.provider_symbol for e in CURATED_UNIVERSE]
    assert len(provider_symbols) == len(set(provider_symbols))


def test_catalog_provider_symbol_sanity():
    for e in CURATED_UNIVERSE:
        ps = e.provider_symbol
        assert ps.endswith(".NS") or ps.startswith("^"), f"{e.symbol}: {ps}"
        assert e.sector.strip(), e.symbol
        assert e.display_name.strip(), e.symbol
        assert e.currency == "INR" and e.country == "IN"
        if e.instrument_type == "index":
            assert ps.startswith("^"), e.symbol


def test_catalog_types_are_valid_enum_values():
    valid = {"equity", "index", "commodity", "etf"}
    assert {e.instrument_type for e in CURATED_UNIVERSE} <= valid


# --- select_news_symbols (Phase 6 NewsAPI quota guard) ------------------------

UNIVERSE = [f"S{i:02d}" for i in range(10)]


def test_news_selector_priority_first_then_rotation():
    chosen = select_news_symbols(UNIVERSE, held={"S05"}, watched={"S09"}, cap=4, day_index=0)
    assert chosen[:2] == ["S05", "S09"]  # priority in universe order
    assert len(chosen) == 4
    assert len(set(chosen)) == 4


def test_news_selector_rotates_daily():
    day0 = select_news_symbols(UNIVERSE, set(), set(), cap=3, day_index=0)
    day1 = select_news_symbols(UNIVERSE, set(), set(), cap=3, day_index=1)
    assert day0 != day1
    # Over enough days, every symbol gets coverage.
    seen: set[str] = set()
    for day in range(10):
        seen.update(select_news_symbols(UNIVERSE, set(), set(), cap=3, day_index=day))
    assert seen == set(UNIVERSE)


def test_news_selector_cap_and_edges():
    assert select_news_symbols(UNIVERSE, set(), set(), cap=0, day_index=1) == []
    everything = select_news_symbols(UNIVERSE, set(UNIVERSE), set(), cap=100, day_index=3)
    assert everything == UNIVERSE
    # Priority overflow is truncated at the cap.
    capped = select_news_symbols(UNIVERSE, set(UNIVERSE), set(), cap=5, day_index=0)
    assert len(capped) == 5
