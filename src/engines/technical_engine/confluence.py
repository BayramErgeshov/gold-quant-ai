"""Technical Confluence aggregator (TECHNICAL_ANALYSIS.md: final steps).

Combines every Technical Department agent's independent report into one
final Technical Report — per TECHNICAL_ANALYSIS.md: "Every technical
component receives a dynamic weight... Each factor contributes to the
Technical Confidence Score... Only this structured report is passed to
the Chief AI. No direct trade decision is made inside the Technical
Department."

The actual voting/weighting/grading algorithm is shared with the Macro
Department (`src.engines.macro_engine.confluence`) via
`src.core.agents.confluence`, per CODING_STANDARDS.md ("Never duplicate
functionality") — this module only adds the Technical-specific historical
outcome integration and field naming.

Scope: combines the seven agents implemented so far (Market Structure,
Trend, Liquidity, Smart Money, Volatility, Support/Resistance, Price
Action) and, optionally, the Historical Research Engine's outcome
statistics (Phase 5). ICT, Wyckoff, Elliott, Volume Profile, Order Flow,
VWAP and Fibonacci agents follow the same `TechnicalAgent` interface and
are added as additional weighted inputs without changing this module.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.core.agents.confluence import combine_agent_reports
from src.core.technical_analysis.agent import AgentReport
from src.engines.historical_engine.similarity import OutcomeStatistics


@dataclass(frozen=True, slots=True)
class TechnicalReport:
    """The final, combined Technical Department report (TECHNICAL_ANALYSIS.md).

    Attributes:
        bullish_probability: Confidence-weighted share of agents voting bullish.
        bearish_probability: Confidence-weighted share of agents voting bearish.
        neutral_probability: Confidence-weighted share of agents voting neutral.
        technical_confidence: Average confidence across directional (non-neutral) agents.
        technical_quality_grade: Institutional grade derived from `technical_confidence`.
        strongest_supporting_factors: Every agent's supporting evidence, pooled.
        strongest_opposing_factors: Every agent's opposing evidence, pooled.
        agent_reports: The individual reports this confluence was built from.
        historical_win_rate: Win rate from the Historical Research Engine's
            similarity search, if supplied and blended into `technical_confidence`.
    """

    bullish_probability: float
    bearish_probability: float
    neutral_probability: float
    technical_confidence: float
    technical_quality_grade: str
    strongest_supporting_factors: list[str]
    strongest_opposing_factors: list[str]
    agent_reports: list[AgentReport]
    historical_win_rate: float | None = None


class TechnicalConfluence:
    """Combines independent Technical Department agent reports into one report."""

    def __init__(self, weights: dict[str, float] | None = None) -> None:
        """Initialize the aggregator.

        Args:
            weights: Optional per-agent weight override, keyed by
                `AgentReport.agent_name`. Agents not listed default to
                1.0. TECHNICAL_ANALYSIS.md: "Weights are not fixed...
                evolve after statistical validation" — the actual dynamic
                learning of these weights belongs to the Self Learning
                Engine (a later roadmap phase); this parameter is the
                hook that will consume its output.
        """
        self._weights = weights or {}

    def combine(
        self,
        reports: list[AgentReport],
        *,
        historical_outcome: OutcomeStatistics | None = None,
    ) -> TechnicalReport:
        """Combine independent agent reports into one final Technical Report.

        Args:
            reports: Every agent's independent `AgentReport`.
            historical_outcome: Optional forward-return statistics from
                the Historical Research Engine's similarity search
                (Phase 5), blended into the overall confidence when given.

        Returns:
            The combined `TechnicalReport`.
        """
        historical_win_rate = (
            historical_outcome.win_rate
            if historical_outcome is not None and historical_outcome.sample_size > 0
            else None
        )
        vote = combine_agent_reports(
            reports, weights=self._weights, historical_win_rate=historical_win_rate
        )

        return TechnicalReport(
            bullish_probability=vote.bullish_probability,
            bearish_probability=vote.bearish_probability,
            neutral_probability=vote.neutral_probability,
            technical_confidence=vote.confidence,
            technical_quality_grade=vote.quality_grade,
            strongest_supporting_factors=vote.strongest_supporting_factors,
            strongest_opposing_factors=vote.strongest_opposing_factors,
            agent_reports=vote.agent_reports,
            historical_win_rate=vote.historical_win_rate,
        )
