"""AI-evaluation unit tests: the pure compute_* helpers."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

from app.services.evaluation import (
    compute_agent_stats,
    compute_forecast_accuracy,
    compute_recommendation_success,
    compute_usage,
)


def test_forecast_accuracy_mape_and_bias():
    rows = [
        ("kronos", 102.0, 100.0),  # +2%
        ("kronos", 98.0, 100.0),  # -2%
        ("baseline", 110.0, 100.0),  # +10%
        ("kronos", 100.0, 0.0),  # zero actual -> skipped
    ]
    out = compute_forecast_accuracy(rows)
    assert out["evaluated_points"] == 3
    assert out["models"]["kronos"] == {"evaluated_points": 2, "mape_pct": 2.0, "bias_pct": 0.0}
    assert out["models"]["baseline"]["mape_pct"] == 10.0
    assert compute_forecast_accuracy([]) == {"models": {}, "evaluated_points": 0}


def _run(
    status: str = "completed",
    action: str = "BUY",
    confidence: float = 0.7,
    entry: float | None = 100.0,
    instrument_id: uuid.UUID | None = None,
    usage: dict | None = None,
    seconds: float | None = 60.0,
) -> SimpleNamespace:
    started = datetime(2026, 7, 16, 10, 0, tzinfo=UTC)
    return SimpleNamespace(
        id=uuid.uuid4(),
        instrument_id=instrument_id or uuid.uuid4(),
        status=status,
        final_decision=(
            {"action": action, "confidence": confidence} if status == "completed" else None
        ),
        context_snapshot=(
            {"price_summary": {"last_close": entry}} if entry is not None else None
        ),
        token_usage=usage,
        started_at=started,
        finished_at=(
            started.replace(minute=1) if seconds else None
        ),
    )


def test_agent_stats_mix_confidence_agreement():
    runs = [
        _run(action="BUY", confidence=0.8),
        _run(action="HOLD", confidence=0.6),
        _run(status="failed"),
    ]
    stances = {
        runs[0].id: {"technical_analyst": "bullish", "news_analyst": "bullish"},
        runs[1].id: {"technical_analyst": "bullish", "news_analyst": "bearish"},
    }
    out = compute_agent_stats(runs, stances)
    assert out["runs_by_status"] == {"completed": 2, "failed": 1}
    assert out["action_mix"] == {"BUY": 1, "HOLD": 1}
    assert out["avg_confidence"] == 0.7
    assert out["stance_agreement_pct"] == 50.0
    assert out["stance_pairs_evaluated"] == 2


def test_agent_stats_empty():
    out = compute_agent_stats([], {})
    assert out["avg_confidence"] is None
    assert out["stance_agreement_pct"] is None


def test_recommendation_success_directional():
    inst_up, inst_down = uuid.uuid4(), uuid.uuid4()
    runs = [
        _run(action="BUY", entry=100.0, instrument_id=inst_up),  # 110 now: +10% win
        _run(action="SELL", entry=100.0, instrument_id=inst_up),  # price rose: -10% loss
        _run(action="SELL", entry=100.0, instrument_id=inst_down),  # 90 now: +10% win
        _run(action="HOLD", entry=100.0, instrument_id=inst_up),  # HOLD skipped
        _run(action="BUY", entry=None, instrument_id=inst_up),  # no snapshot skipped
    ]
    closes = {inst_up: 110.0, inst_down: 90.0}
    out = compute_recommendation_success(runs, closes)
    assert out["evaluated"] == 3
    assert out["success_rate"] == round(2 / 3, 3)
    assert out["by_action"]["BUY"]["avg_return_pct"] == 10.0
    assert out["by_action"]["SELL"]["n"] == 2
    assert out["by_action"]["SELL"]["avg_return_pct"] == 0.0  # -10 and +10


def test_usage_totals_and_cost(monkeypatch):
    from app.core import config

    settings = config.get_settings()
    monkeypatch.setattr(settings, "llm_cost_input_per_1m", 1.0)
    monkeypatch.setattr(settings, "llm_cost_output_per_1m", 10.0)
    runs = [
        _run(usage={"calls": 7, "input_tokens": 500_000, "output_tokens": 100_000}),
        _run(usage={"calls": 7, "input_tokens": 500_000, "output_tokens": 100_000}),
        _run(status="failed", usage=None, seconds=None),
    ]
    out = compute_usage(runs, avg_msg_latency_ms=1234.5)
    assert out["runs_window"] == 3
    assert out["llm_calls"] == 14
    assert out["input_tokens"] == 1_000_000
    assert out["output_tokens"] == 200_000
    assert out["est_cost_usd"] == 3.0  # 1M*1.0/1M + 0.2M*10/1M = 1 + 2
    assert out["avg_run_seconds"] == 60.0
    assert out["avg_message_latency_ms"] == 1234
