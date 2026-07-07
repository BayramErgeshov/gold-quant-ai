"""Cross-department probability aggregation for the Statistics Engine.

Per DECISION_ENGINE.md "Consensus": "Each department votes independently...
Decision Engine combines them." Combines every department's `CombinedVote`
(Technical, Macro, News, Historical, ML) into one overall probability
distribution — the input the future Chief AI (a later roadmap phase) will
use for its BUY/SELL/WAIT decision, per DECISION_ENGINE.md "Estimate
Probability". Each individual department's own vote is already computed by
`src.core.agents.confluence.combine_agent_reports`; this module operates one
level up, combining votes across departments rather than agents within one.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.core.agents.confluence import CombinedVote

_DEFAULT_WEIGHT = 1.0


@dataclass(frozen=True, slots=True)
class ProbabilityEstimate:
    """An overall bull/bear/neutral probability distribution across departments.

    Attributes:
        bullish_probability: Confidence-and-weight-adjusted share favoring "bullish".
        bearish_probability: Confidence-and-weight-adjusted share favoring "bearish".
        neutral_probability: Confidence-and-weight-adjusted share favoring "neutral".
        department_votes: Every department's own vote this estimate was built from.
    """

    bullish_probability: float
    bearish_probability: float
    neutral_probability: float
    department_votes: dict[str, CombinedVote] = field(default_factory=dict)


def combine_department_votes(
    votes: dict[str, CombinedVote], *, weights: dict[str, float] | None = None
) -> ProbabilityEstimate:
    """Combine every department's vote into one overall probability distribution.

    Args:
        votes: Each department's `CombinedVote`, keyed by department name
            (e.g. "technical", "macro", "news", "historical", "ml").
        weights: Optional per-department weight override; departments not
            listed default to 1.0 (DECISION_ENGINE.md "Weighting": weights
            are dynamic — this is the pluggable seam for that).

    Returns:
        A department-agnostic `ProbabilityEstimate`. All-neutral if `votes`
        is empty, or if every department's confidence is 0 — never a
        fabricated directional estimate with no supporting evidence.
    """
    if not votes:
        return ProbabilityEstimate(
            bullish_probability=0.0, bearish_probability=0.0, neutral_probability=1.0
        )

    resolved_weights = weights or {}
    bullish = bearish = neutral = 0.0
    total_weight = 0.0

    for department, vote in votes.items():
        weight = resolved_weights.get(department, _DEFAULT_WEIGHT) * vote.confidence
        bullish += vote.bullish_probability * weight
        bearish += vote.bearish_probability * weight
        neutral += vote.neutral_probability * weight
        total_weight += weight

    if total_weight <= 0:
        return ProbabilityEstimate(
            bullish_probability=0.0,
            bearish_probability=0.0,
            neutral_probability=1.0,
            department_votes=dict(votes),
        )

    return ProbabilityEstimate(
        bullish_probability=bullish / total_weight,
        bearish_probability=bearish / total_weight,
        neutral_probability=neutral / total_weight,
        department_votes=dict(votes),
    )
