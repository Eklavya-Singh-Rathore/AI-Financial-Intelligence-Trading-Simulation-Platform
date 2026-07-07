"""Risk manager agent + coded hard limits.

The LLM reviews the trader's proposal, but the final numbers pass through
:func:`apply_hard_limits`, which can only tighten - an approving LLM can never
loosen the coded constraints (max position size, drawdown veto).
"""

from __future__ import annotations

from app.agents.base import Agent
from app.agents.context import RunContext
from app.agents.outputs import RiskAssessment
from app.core.config import get_settings


class RiskManager(Agent):
    name = "risk_manager"
    output_model = RiskAssessment

    def system_prompt(self, ctx: RunContext) -> str:
        settings = get_settings()
        return (
            "Role: risk manager with veto power. Review the trader's proposal against "
            "the evidence: backtest drawdown/Sharpe, volatility, forecast uncertainty, "
            "news risk. Verdicts: approve (size stands), reduce (give a smaller "
            "adjusted_size_pct), veto (no trade). Firm limits you must respect: "
            f"max position {settings.max_position_pct}% of capital; strategies whose "
            f"backtest max drawdown exceeds {settings.risk_max_drawdown_veto_pct}% "
            "deserve extreme caution. You may only keep or shrink the trader's size, "
            "never increase it."
        )

    def user_prompt(self, ctx: RunContext) -> str:
        return (
            f"{ctx.market_brief()}\n\n"
            f"Trader proposal under review: {ctx.proposal}\n\n"
            "Deliver your risk assessment: verdict (approve/reduce/veto), "
            "adjusted_size_pct, concerns, rationale."
        )


def apply_hard_limits(proposal: dict, assessment: dict, backtest: dict) -> dict:
    """Enforce coded risk rules over the LLM outputs. Returns the effective
    {action, size_pct, risk_verdict, limited_by} decision inputs."""
    settings = get_settings()
    action = proposal.get("action", "HOLD")
    trader_size = float(proposal.get("size_pct", 0.0))
    adjusted = float(assessment.get("adjusted_size_pct", trader_size))
    verdict = assessment.get("verdict", "veto")
    limited_by: list[str] = []

    # LLM may only tighten relative to the trader.
    size = min(trader_size, adjusted)
    if adjusted > trader_size:
        limited_by.append("risk_cannot_increase_size")

    # Hard cap on position size.
    if size > settings.max_position_pct:
        size = settings.max_position_pct
        limited_by.append("max_position_pct")

    # Drawdown veto from backtest evidence. FAIL CLOSED (audit MED-2): when the
    # evidence is missing entirely, the veto cannot fire - so halve the size
    # instead of silently proceeding with weaker risk backing.
    max_dd = backtest.get("metrics", {}).get("max_drawdown_pct")
    if action != "HOLD" and not isinstance(max_dd, int | float):
        size = round(size / 2.0, 2)
        limited_by.append("missing_evidence")
    elif (
        action != "HOLD"
        and isinstance(max_dd, int | float)
        and max_dd <= -abs(settings.risk_max_drawdown_veto_pct)
    ):
        verdict = "veto"
        limited_by.append("drawdown_veto")

    if verdict == "veto" or action == "HOLD":
        return {
            "action": "HOLD",
            "size_pct": 0.0,
            "risk_verdict": verdict,
            "limited_by": limited_by,
        }
    return {
        "action": action,
        "size_pct": round(size, 2),
        "risk_verdict": verdict,
        "limited_by": limited_by,
    }
