"""Unit tests for cross-department probability aggregation."""

from __future__ import annotations

import pytest

from src.core.agents.confluence import CombinedVote
from src.engines.statistics_engine.probability import combine_department_votes

pytestmark = pytest.mark.unit


def _vote(bullish: float, bearish: float, neutral: float, confidence: float) -> CombinedVote:
    return CombinedVote(
        bullish_probability=bullish,
        bearish_probability=bearish,
        neutral_probability=neutral,
        confidence=confidence,
        quality_grade="A",
        strongest_supporting_factors=[],
        strongest_opposing_factors=[],
    )


def test_returns_all_neutral_for_no_votes() -> None:
    estimate = combine_department_votes({})

    assert estimate.bullish_probability == 0.0
    assert estimate.neutral_probability == 1.0


def test_returns_all_neutral_when_every_confidence_is_zero() -> None:
    votes = {
        "technical": _vote(1.0, 0.0, 0.0, confidence=0.0),
        "macro": _vote(0.0, 1.0, 0.0, confidence=0.0),
    }

    estimate = combine_department_votes(votes)

    assert estimate.neutral_probability == 1.0
    assert estimate.department_votes == votes


def test_combines_two_agreeing_departments() -> None:
    votes = {
        "technical": _vote(0.8, 0.1, 0.1, confidence=0.9),
        "macro": _vote(0.7, 0.2, 0.1, confidence=0.6),
    }

    estimate = combine_department_votes(votes)

    assert estimate.bullish_probability > estimate.bearish_probability
    assert estimate.bullish_probability > 0.7


def test_higher_confidence_department_dominates() -> None:
    votes = {
        "technical": _vote(1.0, 0.0, 0.0, confidence=1.0),
        "macro": _vote(0.0, 1.0, 0.0, confidence=0.01),
    }

    estimate = combine_department_votes(votes)

    assert estimate.bullish_probability > 0.9


def test_custom_weights_shift_the_outcome() -> None:
    votes = {
        "technical": _vote(1.0, 0.0, 0.0, confidence=0.5),
        "macro": _vote(0.0, 1.0, 0.0, confidence=0.5),
    }

    weighted_towards_macro = combine_department_votes(votes, weights={"macro": 5.0})

    assert weighted_towards_macro.bearish_probability > weighted_towards_macro.bullish_probability
