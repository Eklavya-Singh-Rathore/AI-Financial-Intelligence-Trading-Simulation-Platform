"""Portfolio manager agent - writes the final decision record."""

from __future__ import annotations

from app.agents.base import Agent
from app.agents.context import RunContext
from app.agents.outputs import FinalDecision


class PortfolioManager(Agent):
    name = "portfolio_manager"
    output_model = FinalDecision

    def system_prompt(self, ctx: RunContext) -> str:
        return (
            "Role: portfolio manager, final authority. The risk-checked decision "
            "inputs are fixed - your job is to confirm the final action/size (you may "
            "only keep or shrink size, or downgrade to HOLD), set an overall "
            "confidence, and write the definitive summary a client would read. The "
            "summary must reference the strongest evidence on both sides."
        )

    def user_prompt(self, ctx: RunContext) -> str:
        return (
            f"{ctx.market_brief()}\n\n"
            f"Technical: {ctx.technical}\n"
            f"Sentiment: {ctx.sentiment}\n"
            f"Trader proposal: {ctx.proposal}\n"
            f"Risk assessment: {ctx.risk}\n\n"
            "Issue the final decision: action, size_pct, confidence, summary."
        )
