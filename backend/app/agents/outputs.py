"""Structured output contracts for every agent (pydantic + JSON schemas).

Each agent's LLM call requests JSON conforming to one of these models; the
orchestrator validates with pydantic so malformed outputs fail loudly and early.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Stance = Literal["bullish", "bearish", "neutral"]
Action = Literal["BUY", "SELL", "HOLD"]
RiskVerdict = Literal["approve", "reduce", "veto"]


class AnalystOutput(BaseModel):
    report: str = Field(description="Concise analysis in plain prose (<= 200 words).")
    stance: Stance
    confidence: float = Field(ge=0.0, le=1.0)


class SentimentOutput(BaseModel):
    report: str = Field(description="Summary of the news narrative (<= 200 words).")
    sentiment_score: float = Field(ge=-1.0, le=1.0)
    stance: Stance
    confidence: float = Field(ge=0.0, le=1.0)


class DebateOutput(BaseModel):
    argument: str = Field(description="This side's strongest case (<= 180 words).")
    key_points: list[str] = Field(default_factory=list, max_length=5)


class TraderProposal(BaseModel):
    action: Action
    size_pct: float = Field(ge=0.0, le=100.0, description="% of portfolio capital.")
    time_horizon_days: int = Field(ge=1, le=365)
    rationale: str


class RiskAssessment(BaseModel):
    verdict: RiskVerdict
    adjusted_size_pct: float = Field(ge=0.0, le=100.0)
    concerns: list[str] = Field(default_factory=list, max_length=6)
    rationale: str


class FinalDecision(BaseModel):
    action: Action
    size_pct: float = Field(ge=0.0, le=100.0)
    confidence: float = Field(ge=0.0, le=1.0)
    summary: str = Field(description="Final recommendation summary (<= 150 words).")


def json_schema_for(model: type[BaseModel]) -> dict:
    """Plain JSON schema (no $defs indirection beyond what pydantic emits)."""
    return model.model_json_schema()
