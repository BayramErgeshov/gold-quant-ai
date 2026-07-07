"""Hypothesis generation for the Self Learning Engine.

Per RESEARCH_FRAMEWORK.md "Hypothesis Generation" and SELF_LEARNING_ENGINE.md
"Learning Pipeline": recurring mistake/success factors across multiple
closed trades become testable hypotheses — a single occurrence is an
anecdote, not a hypothesis ("No assumption survives without statistical
validation").
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from src.engines.learning_engine.factor_analysis import TradeFactor

_MIN_OCCURRENCES_FOR_HYPOTHESIS = 3
_HIGH_PRIORITY_MULTIPLIER = 2


@dataclass(frozen=True, slots=True)
class Hypothesis:
    """A single, testable improvement hypothesis.

    Per RESEARCH_FRAMEWORK.md "Hypothesis Generation": every hypothesis
    contains a Question, Motivation, Supporting Evidence, Expected
    Outcome, Validation Plan, Success/Failure Criteria and Priority.
    """

    question: str
    motivation: str
    supporting_evidence: str
    expected_outcome: str
    validation_plan: str
    success_criteria: str
    failure_criteria: str
    priority: str


def generate_hypotheses_from_factors(
    factors: list[TradeFactor], *, min_occurrences: int = _MIN_OCCURRENCES_FOR_HYPOTHESIS
) -> list[Hypothesis]:
    """Turn recurring factors across many trades into testable hypotheses.

    Args:
        factors: Every mistake/success factor identified across a batch
            of reviewed trades.
        min_occurrences: Minimum number of times a factor must recur to
            justify a hypothesis.

    Returns:
        One `Hypothesis` per factor name that recurred at least
        `min_occurrences` times, most frequent first.
    """
    counts = Counter(factor.name for factor in factors)
    recurring = [name for name, count in counts.most_common() if count >= min_occurrences]

    return [
        Hypothesis(
            question=f"Does the recurring factor {name!r} systematically affect outcomes?",
            motivation=f"{name!r} was identified in {counts[name]} reviewed trades.",
            supporting_evidence=f"{counts[name]} occurrences across reviewed closed trades.",
            expected_outcome=(
                f"Confirming or rejecting whether {name!r} should change decision weighting."
            ),
            validation_plan=(
                "Backtest with and without this factor's influence across multiple "
                "market regimes (SELF_LEARNING_ENGINE.md 'Strategy Validation')."
            ),
            success_criteria="Statistically significant improvement in a held-out test period.",
            failure_criteria="No significant difference, or a significant regression.",
            priority=(
                "P1" if counts[name] >= min_occurrences * _HIGH_PRIORITY_MULTIPLIER else "P2"
            ),
        )
        for name in recurring
    ]
