"""Pydantic schemas for the agents API."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AgentRunRequest(BaseModel):
    symbol: str = Field(description="Registry symbol, e.g. 'RELIANCE', 'NIFTY50'.")
    debate_rounds: int = Field(default=1, ge=1, le=3)


class AgentRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    symbol: str
    status: str
    trigger: str
    llm_provider: str | None = None
    debate_rounds: int
    final_decision: dict | None = None
    token_usage: dict | None = None
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime


class AgentMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    seq: int
    agent_name: str
    content: str
    structured: dict | None = None
    provider: str | None = None
    model: str | None = None
    usage: dict | None = None
    latency_ms: int | None = None
    created_at: datetime
