"""Explainability (Phase 5): compose a recommendation explanation, no LLM.

Everything here is DERIVED from what the pipeline already persisted - the
run's ``final_decision``, its ``context_snapshot`` (decision inputs captured
at gather time), and each agent's structured message output. No model call,
no recomputation: the explanation reflects the decision as it was made.
Old runs (pre-snapshot) degrade gracefully to message-derived sections.
"""

from __future__ import annotations

from typing import Any


def _latest_by_agent(messages: list[Any]) -> dict[str, Any]:
    """Latest message per agent (later seq wins; debate agents keep all)."""
    latest: dict[str, Any] = {}
    for msg in sorted(messages, key=lambda m: m.seq):
        latest[msg.agent_name] = msg
    return latest


def _debate(messages: list[Any], agent_name: str) -> list[dict]:
    out = []
    for msg in sorted(messages, key=lambda m: m.seq):
        if msg.agent_name == agent_name and msg.structured:
            out.append(
                {
                    "argument": msg.structured.get("argument"),
                    "key_points": msg.structured.get("key_points") or [],
                }
            )
    return out


def compose_explanation(run: Any, messages: list[Any]) -> dict[str, Any]:
    """Structured why/indicators/news/forecast/backtest/risk for one run."""
    snapshot: dict = run.context_snapshot or {}
    latest = _latest_by_agent(messages)

    def structured(agent: str) -> dict:
        msg = latest.get(agent)
        return dict(msg.structured) if msg is not None and msg.structured else {}

    decision: dict = run.final_decision or {}
    trader = structured("trader")
    risk = structured("risk_manager")
    technical = structured("technical_analyst")
    sentiment = structured("news_analyst")

    why = [
        part
        for part in (
            decision.get("summary"),
            trader.get("rationale"),
            risk.get("rationale"),
        )
        if part
    ]

    return {
        "run_id": str(run.id),
        "symbol": run.symbol,
        "status": run.status,
        "as_of": snapshot.get("as_of"),
        "decision": decision,
        "why": why,
        "technical": {
            "stance": technical.get("stance"),
            "confidence": technical.get("confidence"),
            "report": technical.get("report"),
        },
        "news": {
            "stance": sentiment.get("stance"),
            "sentiment_score": sentiment.get("sentiment_score"),
            "confidence": sentiment.get("confidence"),
            "report": sentiment.get("report"),
            "headlines": snapshot.get("headlines") or [],
        },
        "debate": {
            "bull": _debate(messages, "bull_researcher"),
            "bear": _debate(messages, "bear_researcher"),
        },
        "risk": {
            "verdict": risk.get("verdict"),
            "adjusted_size_pct": risk.get("adjusted_size_pct"),
            "concerns": risk.get("concerns") or [],
            "rationale": risk.get("rationale"),
            "limited_by": decision.get("limited_by") or [],
        },
        "indicators": snapshot.get("indicators") or {},
        "price_summary": snapshot.get("price_summary") or {},
        "forecast": snapshot.get("forecast") or {},
        "backtest": snapshot.get("backtest") or {},
        "has_snapshot": bool(snapshot),
    }
