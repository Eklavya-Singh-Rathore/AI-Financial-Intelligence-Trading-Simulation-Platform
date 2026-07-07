"""Chat service tests: pure helpers fast; full round-trip is db-marked."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

from app.services.chat_service import build_user_prompt, detect_symbols


def _inst(symbol: str, name: str) -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), symbol=symbol, display_name=name)


UNIVERSE = [
    _inst("RELIANCE", "Reliance Industries"),
    _inst("TCS", "Tata Consultancy Services"),
    _inst("NIFTY50", "NIFTY 50"),
    _inst("GOLD", "Nippon India ETF Gold BeES"),
    _inst("ITC", "ITC"),
]


def test_detect_symbols_by_registry_symbol():
    hits = detect_symbols("how does RELIANCE look vs tcs?", UNIVERSE)
    assert [i.symbol for i in hits] == ["RELIANCE", "TCS"]


def test_detect_symbols_by_display_name():
    hits = detect_symbols("what's happening with reliance industries lately", UNIVERSE)
    assert [i.symbol for i in hits] == ["RELIANCE"]


def test_detect_symbols_word_boundaries():
    # 'gold' inside a longer word must not match; 'itc' inside 'pitch' must not.
    hits = detect_symbols("the goldilocks pitch continues", UNIVERSE)
    assert hits == []


def test_detect_symbols_caps_at_three():
    hits = detect_symbols("compare RELIANCE TCS NIFTY50 GOLD ITC", UNIVERSE)
    assert len(hits) == 3


def test_build_user_prompt_sections_and_boundaries():
    prompt = build_user_prompt(
        message="How is RELIANCE doing?",
        market_lines=["RELIANCE ... last_close 1308.4"],
        decision_lines=["[2026-07-07] TCS: HOLD size=0.0%"],
        memory_notes=["[2026-07-07] portfolio_manager: HOLD ..."],
        history=[("user", "hi"), ("assistant", "hello")],
    )
    assert "Live market data:" in prompt
    assert "Recent agent-pipeline decisions:" in prompt
    assert "<untrusted-data>" in prompt  # memory rendered inside the boundary
    assert prompt.index("user: hi") < prompt.index("User question:")
    assert prompt.rstrip().endswith("How is RELIANCE doing?")


def test_build_user_prompt_minimal():
    prompt = build_user_prompt("hello", [], [], [], [])
    assert prompt == "User question: hello"
