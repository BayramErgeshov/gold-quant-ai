"""Structured report format shared by every research agent.

Per AGENT_SYSTEM.md: "Every agent produces an independent report... Every
report contains Findings, Confidence, Supporting Evidence, Opposing
Evidence, Historical Statistics, Recommendation, Unknowns... Agents never
hide uncertainty." Used by both the Technical Department
(`src.core.technical_analysis`) and Macro Department
(`src.core.macro_analysis`) agents, so the format is defined once here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Bias = Literal["bullish", "bearish", "neutral"]


@dataclass(frozen=True, slots=True)
class AgentReport:
    """Structured output every research agent produces (AGENT_SYSTEM.md).

    Attributes:
        agent_name: The producing agent's name.
        bias: The agent's directional read, independent of any other agent.
        confidence: Confidence in [0.0, 1.0].
        supporting_evidence: Facts supporting `bias`.
        opposing_evidence: Facts that argue against `bias`.
        unknowns: Things the agent explicitly could not determine, rather
            than silently guessing (AGENT_SYSTEM.md: "Agents never hide
            uncertainty").
        metrics: Raw computed values backing the report, for explainability.
    """

    agent_name: str
    bias: Bias
    confidence: float
    supporting_evidence: list[str] = field(default_factory=list)
    opposing_evidence: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)
