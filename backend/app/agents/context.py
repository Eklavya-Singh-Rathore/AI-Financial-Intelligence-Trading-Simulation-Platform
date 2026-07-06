"""RunContext - everything the agents see, gathered deterministically upfront."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RunContext:
    """Accumulating context for one pipeline run.

    The gather step fills the data fields; each agent appends its output so
    later agents can build on earlier ones.
    """

    symbol: str
    display_name: str
    as_of: str  # ISO date of the latest bar

    # --- gathered data (deterministic) ---
    price_summary: dict = field(default_factory=dict)
    indicators: dict = field(default_factory=dict)
    forecast: dict = field(default_factory=dict)
    backtest: dict = field(default_factory=dict)
    headlines: list[str] = field(default_factory=list)
    memory_notes: list[str] = field(default_factory=list)

    # --- agent outputs (accumulated) ---
    technical: dict = field(default_factory=dict)
    sentiment: dict = field(default_factory=dict)
    bull_arguments: list[dict] = field(default_factory=list)
    bear_arguments: list[dict] = field(default_factory=list)
    proposal: dict = field(default_factory=dict)
    risk: dict = field(default_factory=dict)

    def market_brief(self) -> str:
        """Shared data section rendered into every agent prompt."""
        lines = [
            f"Instrument: {self.display_name} ({self.symbol}) | data as of {self.as_of}",
            f"Price summary: {self.price_summary}",
            f"Latest indicators: {self.indicators}",
            f"Model forecast: {self.forecast}",
            f"Strategy backtest evidence (SMA crossover): {self.backtest}",
        ]
        if self.headlines:
            lines.append("Recent headlines:\n" + "\n".join(f"- {h}" for h in self.headlines))
        else:
            lines.append("Recent headlines: none available")
        if self.memory_notes:
            lines.append(
                "Notes from previous analyses (memory):\n"
                + "\n".join(f"- {n}" for n in self.memory_notes)
            )
        return "\n\n".join(lines)

    def debate_transcript(self) -> str:
        rounds = []
        for i in range(max(len(self.bull_arguments), len(self.bear_arguments))):
            if i < len(self.bull_arguments):
                rounds.append(f"BULL (round {i + 1}): {self.bull_arguments[i].get('argument', '')}")
            if i < len(self.bear_arguments):
                rounds.append(f"BEAR (round {i + 1}): {self.bear_arguments[i].get('argument', '')}")
        return "\n\n".join(rounds) if rounds else "(no debate yet)"
