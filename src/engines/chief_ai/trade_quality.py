"""Trade Quality Engine.

Per the "Trade Quality Engine" production requirement: every potential
trade receives a single 0-100 quality score built entirely from evidence
departments already produced this cycle -- never a fixed indicator rule
(e.g. "RSI > 50", "MACD Cross"). The score combines:

- Confluence strength: how strongly the combined department vote already
  leans toward its dominant direction (`ProbabilityEstimate`, itself
  already a calibrated-weight combination -- see
  `src.engines.statistics_engine.probability.combine_department_votes`).
- Confidence: the same overall confidence Chief AI itself gates on.
- Department reliability: the *measured* historical accuracy of the
  departments actually agreeing with this cycle's dominant direction
  (`src.engines.learning_engine.department_performance`) -- a department
  with a poor track record contributes less to the score even if it
  agrees, which is what makes this "calibrated" rather than a naive
  headcount of agreeing departments.
- Books confluence: how much statistically-validated book knowledge
  supports this setup (`src.repositories.book_claim_repository`, once
  Phase 9's claim validation actually accepts claims -- 0.0 until then,
  never a fabricated boost from unvalidated or absent claims).

Risk Score reuses `src.engines.risk_engine.approval.classify_confidence_level`
(the same tiering the Risk Engine's own approval gate already applies to
`confidence_pct`) rather than inventing a second, parallel risk metric.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.core.agents.confluence import CombinedVote, vote_bias
from src.engines.risk_engine.approval import ConfidenceLevel, classify_confidence_level
from src.engines.statistics_engine.probability import ProbabilityEstimate

_CONFLUENCE_WEIGHT = 40.0
_CONFIDENCE_WEIGHT = 30.0
_RELIABILITY_WEIGHT = 20.0
_BOOKS_WEIGHT = 10.0
_DEFAULT_RELIABILITY = 1.0

# Reuses RISK_ENGINE.md's own "Confidence Levels" tiering
# (`classify_confidence_level`) as the Risk Score, rather than a second,
# parallel risk metric with its own invented thresholds.
_RISK_TIER_SCORES: dict[ConfidenceLevel, float] = {
    "institutional_grade": 100.0,
    "high_quality": 80.0,
    "possible_setup": 55.0,
    "observation_only": 30.0,
    "reject": 0.0,
}


@dataclass(frozen=True, slots=True)
class TradeQualityResult:
    """The Trade Quality Engine's output for one decision cycle.

    Attributes:
        score: Overall trade quality in [0.0, 100.0].
        risk_score: Risk-tier score in [0.0, 100.0], from
            `classify_confidence_level(confidence_pct)`.
        reasoning: Short, factual lines explaining how `score` was built
            -- never a fabricated narrative.
    """

    score: float
    risk_score: float
    reasoning: list[str] = field(default_factory=list)


def compute_trade_quality(
    *,
    probability: ProbabilityEstimate,
    confidence_pct: float,
    department_votes: dict[str, CombinedVote],
    department_reliability: dict[str, float] | None = None,
    books_confluence: float = 0.0,
) -> TradeQualityResult:
    """Compute this cycle's Trade Quality Score and Risk Score.

    Args:
        probability: The combined cross-department probability distribution.
        confidence_pct: Overall decision confidence, in [0.0, 100.0].
        department_votes: Every department's own `CombinedVote` this cycle.
        department_reliability: Each department's measured reliability
            (`src.engines.learning_engine.department_performance`),
            keyed by department name. A department absent here defaults
            to the neutral weight of 1.0 -- not yet measured is not the
            same as unreliable.
        books_confluence: How much validated book knowledge supports this
            setup, in [0.0, 1.0]. Defaults to 0.0 (no contribution) until
            Phase 9's claim validation produces accepted claims to weigh.

    Returns:
        The computed `TradeQualityResult`.
    """
    resolved_reliability = department_reliability or {}
    dominant_bias = (
        "bullish"
        if probability.bullish_probability >= probability.bearish_probability
        else "bearish"
    )
    confluence_strength = max(probability.bullish_probability, probability.bearish_probability)

    agreeing_reliabilities = [
        resolved_reliability.get(name, _DEFAULT_RELIABILITY)
        for name, vote in department_votes.items()
        if vote_bias(vote) == dominant_bias
    ]
    average_reliability = (
        sum(agreeing_reliabilities) / len(agreeing_reliabilities)
        if agreeing_reliabilities
        else _DEFAULT_RELIABILITY
    )
    books_component = max(0.0, min(1.0, books_confluence))

    score = (
        _CONFLUENCE_WEIGHT * confluence_strength
        + _CONFIDENCE_WEIGHT * (confidence_pct / 100.0)
        + _RELIABILITY_WEIGHT * average_reliability
        + _BOOKS_WEIGHT * books_component
    )
    score = max(0.0, min(100.0, score))

    confidence_level = classify_confidence_level(min(100.0, max(0.0, confidence_pct)))
    risk_score = _RISK_TIER_SCORES[confidence_level]

    reasoning = [
        f"confluence_strength:{confluence_strength:.0%}_{dominant_bias}",
        f"department_reliability:{average_reliability:.0%}",
        f"risk_tier:{confidence_level}",
    ]
    if books_component > 0:
        reasoning.append(f"books_support:{books_component:.0%}")

    return TradeQualityResult(score=score, risk_score=risk_score, reasoning=reasoning)
