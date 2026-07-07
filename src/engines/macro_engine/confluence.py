"""Macro Confluence aggregator (AGENT_SYSTEM.md: Macro Department).

Combines every Macro Department agent's independent report (Interest Rate,
Inflation, Employment, Dollar Index, Bond Yield, ...) into one final Macro
Report — the same AGENT_SYSTEM.md pattern as
`src.engines.technical_engine.confluence.TechnicalConfluence`, sharing its
voting/weighting/grading algorithm via `src.core.agents.confluence` per
CODING_STANDARDS.md ("Never duplicate functionality").
"""

from __future__ import annotations

from dataclasses import dataclass

from src.core.agents.confluence import combine_agent_reports
from src.core.agents.report import AgentReport


@dataclass(frozen=True, slots=True)
class MacroReport:
    """The final, combined Macro Department report.

    Attributes:
        bullish_probability: Confidence-weighted share of agents voting bullish.
        bearish_probability: Confidence-weighted share of agents voting bearish.
        neutral_probability: Confidence-weighted share of agents voting neutral.
        macro_confidence: Average confidence across directional (non-neutral) agents.
        macro_quality_grade: Institutional grade derived from `macro_confidence`.
        strongest_supporting_factors: Every agent's supporting evidence, pooled.
        strongest_opposing_factors: Every agent's opposing evidence, pooled.
        agent_reports: The individual reports this confluence was built from.
    """

    bullish_probability: float
    bearish_probability: float
    neutral_probability: float
    macro_confidence: float
    macro_quality_grade: str
    strongest_supporting_factors: list[str]
    strongest_opposing_factors: list[str]
    agent_reports: list[AgentReport]


class MacroConfluence:
    """Combines independent Macro Department agent reports into one report."""

    def __init__(self, weights: dict[str, float] | None = None) -> None:
        """Initialize the aggregator.

        Args:
            weights: Optional per-agent weight override, keyed by
                `AgentReport.agent_name`. Agents not listed default to 1.0.
        """
        self._weights = weights or {}

    def combine(self, reports: list[AgentReport]) -> MacroReport:
        """Combine independent agent reports into one final Macro Report.

        Args:
            reports: Every agent's independent `AgentReport`.

        Returns:
            The combined `MacroReport`.
        """
        vote = combine_agent_reports(reports, weights=self._weights)

        return MacroReport(
            bullish_probability=vote.bullish_probability,
            bearish_probability=vote.bearish_probability,
            neutral_probability=vote.neutral_probability,
            macro_confidence=vote.confidence,
            macro_quality_grade=vote.quality_grade,
            strongest_supporting_factors=vote.strongest_supporting_factors,
            strongest_opposing_factors=vote.strongest_opposing_factors,
            agent_reports=vote.agent_reports,
        )
