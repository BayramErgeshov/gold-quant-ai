"""Generic confluence algorithm for combining independent agent reports.

Shared by the Technical Department (`src.engines.technical_engine.confluence`)
and Macro Department (`src.engines.macro_engine.confluence`) aggregators,
per CODING_STANDARDS.md ("Never duplicate functionality") — both follow the
identical AGENT_SYSTEM.md pattern: "Every department votes independently...
Chief AI evaluates Agreement, Disagreement, Evidence Strength... Confidence...
Uncertainty."
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.core.agents.report import AgentReport, Bias

_GRADE_THRESHOLDS: tuple[tuple[float, str], ...] = (
    (0.85, "AAA"),
    (0.75, "AA"),
    (0.65, "A"),
    (0.55, "BBB"),
    (0.45, "BB"),
    (0.35, "B"),
)
_DEFAULT_WEIGHT = 1.0


@dataclass(frozen=True, slots=True)
class CombinedVote:
    """The result of combining independent agent reports (department-agnostic).

    Attributes:
        bullish_probability: Confidence-weighted share of agents voting bullish.
        bearish_probability: Confidence-weighted share of agents voting bearish.
        neutral_probability: Confidence-weighted share of agents voting neutral.
        confidence: Average confidence across directional (non-neutral) agents,
            optionally blended with a historical outcome win rate.
        quality_grade: Institutional grade derived from `confidence`.
        strongest_supporting_factors: Every agent's supporting evidence, pooled.
        strongest_opposing_factors: Every agent's opposing evidence, pooled.
        agent_reports: The individual reports this vote was built from.
        historical_win_rate: The win rate blended into `confidence`, if supplied.
    """

    bullish_probability: float
    bearish_probability: float
    neutral_probability: float
    confidence: float
    quality_grade: str
    strongest_supporting_factors: list[str]
    strongest_opposing_factors: list[str]
    agent_reports: list[AgentReport] = field(default_factory=list)
    historical_win_rate: float | None = None


def grade_from_confidence(confidence: float) -> str:
    """Map a confidence score to an institutional quality grade.

    Args:
        confidence: Confidence in [0.0, 1.0].

    Returns:
        A grade from "AAA" (highest) down to "C" (lowest).
    """
    for threshold, grade in _GRADE_THRESHOLDS:
        if confidence >= threshold:
            return grade
    return "C"


def combine_agent_reports(
    reports: list[AgentReport],
    *,
    weights: dict[str, float] | None = None,
    historical_win_rate: float | None = None,
) -> CombinedVote:
    """Combine independent agent reports into a department-agnostic vote.

    Args:
        reports: Every agent's independent `AgentReport`.
        weights: Optional per-agent weight override, keyed by
            `AgentReport.agent_name`. Agents not listed default to 1.0.
        historical_win_rate: Optional win rate (e.g. from the Historical
            Research Engine's similarity search) blended into the overall
            confidence when given.

    Returns:
        The combined `CombinedVote`.
    """
    if not reports:
        return CombinedVote(
            bullish_probability=0.0,
            bearish_probability=0.0,
            neutral_probability=1.0,
            confidence=0.0,
            quality_grade="C",
            strongest_supporting_factors=[],
            strongest_opposing_factors=[],
        )

    resolved_weights = weights or {}
    bullish_probability, bearish_probability, neutral_probability = _vote(reports, resolved_weights)
    confidence = _average_directional_confidence(reports)

    if historical_win_rate is not None:
        confidence = (confidence + historical_win_rate) / 2

    return CombinedVote(
        bullish_probability=bullish_probability,
        bearish_probability=bearish_probability,
        neutral_probability=neutral_probability,
        confidence=confidence,
        quality_grade=grade_from_confidence(confidence),
        strongest_supporting_factors=sorted(
            evidence for report in reports for evidence in report.supporting_evidence
        ),
        strongest_opposing_factors=sorted(
            evidence for report in reports for evidence in report.opposing_evidence
        ),
        agent_reports=reports,
        historical_win_rate=historical_win_rate,
    )


def _vote(
    reports: list[AgentReport], weights: dict[str, float]
) -> tuple[float, float, float]:
    """Confidence-and-weight-adjusted vote share for each bias."""
    bias_weight: dict[Bias, float] = {"bullish": 0.0, "bearish": 0.0, "neutral": 0.0}
    total_weight = 0.0

    for report in reports:
        weight = weights.get(report.agent_name, _DEFAULT_WEIGHT) * report.confidence
        bias_weight[report.bias] += weight
        total_weight += weight

    if total_weight <= 0:
        return 0.0, 0.0, 1.0

    return (
        bias_weight["bullish"] / total_weight,
        bias_weight["bearish"] / total_weight,
        bias_weight["neutral"] / total_weight,
    )


def _average_directional_confidence(reports: list[AgentReport]) -> float:
    directional = [report for report in reports if report.bias != "neutral"]
    if not directional:
        return 0.0
    return sum(report.confidence for report in directional) / len(directional)
