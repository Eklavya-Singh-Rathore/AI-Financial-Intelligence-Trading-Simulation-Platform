"""Agent base class - prompt assembly + validated structured LLM call."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.agents.context import RunContext
from app.agents.outputs import json_schema_for
from app.llm.base import LLMClient, LLMError, LLMResponse
from pydantic import BaseModel, ValidationError


@dataclass
class AgentResult:
    agent_name: str
    content: str  # human-readable report/argument text
    structured: dict  # validated model dump
    response: LLMResponse  # provider/usage/latency for persistence


class Agent(ABC):
    """One pipeline step backed by a single structured LLM call."""

    name: str = "agent"
    output_model: type[BaseModel]

    PREAMBLE = (
        "You are part of a multi-agent equity analysis team for Indian markets. "
        "This is decision-support research only - no real orders are placed. "
        "Ground every claim in the data provided; do not invent numbers."
    )

    @abstractmethod
    def system_prompt(self, ctx: RunContext) -> str:
        raise NotImplementedError

    @abstractmethod
    def user_prompt(self, ctx: RunContext) -> str:
        raise NotImplementedError

    def run(self, llm: LLMClient, ctx: RunContext) -> AgentResult:
        schema = json_schema_for(self.output_model)
        response = llm.complete(
            system=f"{self.PREAMBLE}\n\n{self.system_prompt(ctx)}",
            messages=[{"role": "user", "content": self.user_prompt(ctx)}],
            json_schema=schema,
        )
        try:
            validated = self.output_model.model_validate(response.parsed)
        except ValidationError as exc:
            raise LLMError(
                f"{self.name} returned JSON not matching {self.output_model.__name__}: {exc}"
            ) from exc
        structured = validated.model_dump()
        content = str(
            structured.get("report")
            or structured.get("argument")
            or structured.get("rationale")
            or structured.get("summary")
            or response.text
        )
        return AgentResult(
            agent_name=self.name, content=content, structured=structured, response=response
        )
