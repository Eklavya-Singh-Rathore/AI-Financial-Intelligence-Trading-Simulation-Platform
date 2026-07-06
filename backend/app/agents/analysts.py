"""Analyst agents: technical (price/indicators) and news/sentiment."""

from __future__ import annotations

from app.agents.base import Agent
from app.agents.context import RunContext
from app.agents.outputs import AnalystOutput, SentimentOutput


class TechnicalAnalyst(Agent):
    name = "technical_analyst"
    output_model = AnalystOutput

    def system_prompt(self, ctx: RunContext) -> str:
        return (
            "Role: senior technical analyst. Interpret the price action, returns, "
            "moving averages, RSI, MACD, Bollinger position, the model forecast, and "
            "the strategy backtest evidence. Weigh trend vs. momentum vs. mean-reversion. "
            "Be specific about which numbers drive your stance."
        )

    def user_prompt(self, ctx: RunContext) -> str:
        return (
            f"{ctx.market_brief()}\n\n"
            "Produce your technical read of this instrument right now: report, "
            "stance (bullish/bearish/neutral), confidence (0-1)."
        )


class NewsAnalyst(Agent):
    name = "news_analyst"
    output_model = SentimentOutput

    def system_prompt(self, ctx: RunContext) -> str:
        return (
            "Role: financial news and sentiment analyst covering Indian markets. "
            "Assess the recent headlines for this instrument: materiality, direction, "
            "and durability of the narrative. If there is no news, say so and return "
            "a neutral stance with sentiment_score 0 and low confidence."
        )

    def user_prompt(self, ctx: RunContext) -> str:
        return (
            f"{ctx.market_brief()}\n\n"
            "Summarise the news narrative and score it: report, sentiment_score "
            "(-1 very negative .. +1 very positive), stance, confidence (0-1)."
        )
