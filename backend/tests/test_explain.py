"""Explainability composition tests (pure - SimpleNamespace stand-ins)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

from app.agents.explain import compose_explanation


def _msg(seq: int, agent: str, structured: dict | None) -> SimpleNamespace:
    return SimpleNamespace(seq=seq, agent_name=agent, structured=structured)


def _run(**overrides) -> SimpleNamespace:
    base = {
        "id": uuid.uuid4(),
        "symbol": "TCS",
        "status": "completed",
        "final_decision": {
            "action": "BUY",
            "size_pct": 5.0,
            "confidence": 0.7,
            "summary": "Momentum supports entry.",
            "risk_verdict": "approve",
            "limited_by": ["risk_adjusted_size"],
        },
        "context_snapshot": {
            "as_of": "2026-07-16",
            "price_summary": {"last_close": 4100.0},
            "indicators": {"rsi": 61.2, "sma": 4050.1},
            "forecast": {"model": "kronos", "horizon_days": 5, "predicted_closes": [4120.0]},
            "backtest": {"engine": "nautilus", "metrics": {"sharpe": 1.1}},
            "headlines": ["[2026-07-15] (Mint) TCS wins deal"],
        },
    }
    base.update(overrides)
    return SimpleNamespace(**base)


MESSAGES = [
    _msg(1, "technical_analyst", {"report": "Uptrend.", "stance": "bullish", "confidence": 0.8}),
    _msg(2, "news_analyst", {"report": "Positive.", "stance": "bullish", "sentiment_score": 0.4,
                             "confidence": 0.6}),
    _msg(3, "bull_researcher", {"argument": "Buy it.", "key_points": ["momentum"]}),
    _msg(4, "bear_researcher", {"argument": "Too hot.", "key_points": ["valuation"]}),
    _msg(5, "trader", {"action": "BUY", "size_pct": 8.0, "time_horizon_days": 20,
                       "rationale": "Trend plus news."}),
    _msg(6, "risk_manager", {"verdict": "approve", "adjusted_size_pct": 5.0,
                             "concerns": ["concentration"], "rationale": "Size trimmed."}),
    _msg(7, "portfolio_manager", {"action": "BUY", "size_pct": 5.0, "confidence": 0.7,
                                  "summary": "Momentum supports entry."}),
]


def test_compose_full_run():
    ex = compose_explanation(_run(), MESSAGES)
    assert ex["symbol"] == "TCS"
    assert ex["as_of"] == "2026-07-16"
    assert ex["decision"]["action"] == "BUY"
    # why: decision summary + trader rationale + risk rationale, in that order.
    assert ex["why"] == ["Momentum supports entry.", "Trend plus news.", "Size trimmed."]
    assert ex["technical"]["stance"] == "bullish"
    assert ex["news"]["sentiment_score"] == 0.4
    assert ex["news"]["headlines"] == ["[2026-07-15] (Mint) TCS wins deal"]
    assert ex["debate"]["bull"] == [{"argument": "Buy it.", "key_points": ["momentum"]}]
    assert ex["debate"]["bear"][0]["key_points"] == ["valuation"]
    assert ex["risk"]["verdict"] == "approve"
    assert ex["risk"]["limited_by"] == ["risk_adjusted_size"]
    assert ex["indicators"]["rsi"] == 61.2
    assert ex["forecast"]["model"] == "kronos"
    assert ex["backtest"]["metrics"]["sharpe"] == 1.1
    assert ex["has_snapshot"] is True


def test_compose_pre_snapshot_run_degrades():
    ex = compose_explanation(_run(context_snapshot=None), MESSAGES)
    assert ex["has_snapshot"] is False
    assert ex["indicators"] == {}
    assert ex["forecast"] == {}
    assert ex["news"]["headlines"] == []
    # Message-derived sections still populate.
    assert ex["technical"]["stance"] == "bullish"
    assert ex["why"][1] == "Trend plus news."


def test_compose_empty_run():
    run = _run(final_decision=None, context_snapshot=None, status="failed")
    ex = compose_explanation(run, [])
    assert ex["decision"] == {}
    assert ex["why"] == []
    assert ex["debate"] == {"bull": [], "bear": []}
    assert ex["risk"]["concerns"] == []


def test_compose_multi_round_debate_keeps_all_and_latest_wins():
    messages = MESSAGES + [
        _msg(8, "bull_researcher", {"argument": "Round 2 bull.", "key_points": []}),
        _msg(9, "trader", {"action": "BUY", "size_pct": 6.0, "time_horizon_days": 20,
                           "rationale": "Updated view."}),
    ]
    ex = compose_explanation(_run(), messages)
    assert len(ex["debate"]["bull"]) == 2
    assert ex["debate"]["bull"][1]["argument"] == "Round 2 bull."
    assert ex["why"][1] == "Updated view."  # latest trader message wins
