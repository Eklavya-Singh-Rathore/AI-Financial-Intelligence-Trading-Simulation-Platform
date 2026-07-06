"""Trader agent - synthesizes analysis + debate into a concrete proposal."""

from __future__ import annotations

from app.agents.base import Agent
from app.agents.context import RunContext
from app.agents.outputs import TraderProposal


class Trader(Agent):
    name = "trader"
    output_model = TraderProposal

    def system_prompt(self, ctx: RunContext) -> str:
        return (
            "Role: head trader. Weigh the technical read, the news sentiment, and both "
            "sides of the researcher debate, then commit to ONE concrete proposal: "
            "BUY, SELL, or HOLD, with a position size as % of portfolio capital and a "
            "holding horizon in days. Prefer HOLD when evidence is genuinely mixed. "
            "Size positions proportionally to conviction and evidence quality."
        )

    def user_prompt(self, ctx: RunContext) -> str:
        return (
            f"{ctx.market_brief()}\n\n"
            f"Technical analyst view: {ctx.technical}\n"
            f"News analyst view: {ctx.sentiment}\n\n"
            f"Researcher debate:\n{ctx.debate_transcript()}\n\n"
            "State your trading proposal: action, size_pct, time_horizon_days, rationale."
        )
