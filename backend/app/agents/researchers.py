"""Bull and Bear researcher agents - adversarial debate over the analyst reports."""

from __future__ import annotations

from app.agents.base import Agent
from app.agents.context import RunContext
from app.agents.outputs import DebateOutput


class BullResearcher(Agent):
    name = "bull_researcher"
    output_model = DebateOutput

    def system_prompt(self, ctx: RunContext) -> str:
        return (
            "Role: bull-case researcher. Argue the strongest evidence-based case FOR "
            "taking/holding a long position. Engage with the bear's latest points "
            "directly if any exist. Never fabricate data."
        )

    def user_prompt(self, ctx: RunContext) -> str:
        return (
            f"{ctx.market_brief()}\n\n"
            f"Technical analyst view: {ctx.technical}\n"
            f"News analyst view: {ctx.sentiment}\n\n"
            f"Debate so far:\n{ctx.debate_transcript()}\n\n"
            "Give the bull argument for this round."
        )


class BearResearcher(Agent):
    name = "bear_researcher"
    output_model = DebateOutput

    def system_prompt(self, ctx: RunContext) -> str:
        return (
            "Role: bear-case researcher. Argue the strongest evidence-based case "
            "AGAINST a long position (or for reducing/avoiding exposure). Engage with "
            "the bull's latest points directly. Never fabricate data."
        )

    def user_prompt(self, ctx: RunContext) -> str:
        return (
            f"{ctx.market_brief()}\n\n"
            f"Technical analyst view: {ctx.technical}\n"
            f"News analyst view: {ctx.sentiment}\n\n"
            f"Debate so far:\n{ctx.debate_transcript()}\n\n"
            "Give the bear argument for this round."
        )
