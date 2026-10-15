"""Unit tests for the Trade Quality Engine."""

from __future__ import annotations

from src.core.agents.confluence import CombinedVote
from src.engines.chief_ai.trade_quality import compute_trade_quality
from src.engines.statistics_engine.probability import ProbabilityEstimate


def _vote(bullish: float, bearish: float, *, confidence: float = 0.8) -> CombinedVote:
    return CombinedVote(
        bullish_probability=bullish,
        bearish_probability=bearish,
        neutral_probability=max(0.0, 1.0 - bullish - bearish),
        confidence=confidence,
        quality_grade="A",
        strongest_supporting_factors=[],
        strongest_opposing_factors=[],
    )


def test_score_is_bounded_between_zero_and_a_hundred() -> None:
    result = compute_trade_quality(
        probability=ProbabilityEstimate(
            bullish_probability=1.0, bearish_probability=0.0, neutral_probability=0.0
        ),
        confidence_pct=100.0,
        department_votes={"technical": _vote(1.0, 0.0)},
        department_reliability={"technical": 1.0},
    )

    assert 0.0 <= result.score <= 100.0
    assert 0.0 <= result.risk_score <= 100.0


def test_higher_department_reliability_raises_the_score() -> None:
    probability = ProbabilityEstimate(
        bullish_probability=0.7, bearish_probability=0.3, neutral_probability=0.0
    )
    department_votes = {"technical": _vote(0.7, 0.3), "historical": _vote(0.7, 0.3)}

    low_reliability = compute_trade_quality(
        probability=probability,
        confidence_pct=75.0,
        department_votes=department_votes,
        department_reliability={"technical": 0.3, "historical": 0.3},
    )
    high_reliability = compute_trade_quality(
        probability=probability,
        confidence_pct=75.0,
        department_votes=department_votes,
        department_reliability={"technical": 0.95, "historical": 0.95},
    )

    assert high_reliability.score > low_reliability.score


def test_missing_reliability_defaults_to_neutral_one() -> None:
    probability = ProbabilityEstimate(
        bullish_probability=0.6, bearish_probability=0.4, neutral_probability=0.0
    )
    department_votes = {"technical": _vote(0.6, 0.4)}

    result = compute_trade_quality(
        probability=probability,
        confidence_pct=65.0,
        department_votes=department_votes,
        department_reliability=None,
    )
    with_full_reliability = compute_trade_quality(
        probability=probability,
        confidence_pct=65.0,
        department_votes=department_votes,
        department_reliability={"technical": 1.0},
    )

    assert result.score == with_full_reliability.score


def test_only_agreeing_departments_influence_reliability_component() -> None:
    probability = ProbabilityEstimate(
        bullish_probability=0.8, bearish_probability=0.2, neutral_probability=0.0
    )
    department_votes = {
        "technical": _vote(0.8, 0.2),
        "correlation": _vote(0.2, 0.8),  # disagrees with the dominant (bullish) direction
    }

    # A disagreeing department's poor reliability must not drag the score
    # down -- only departments that actually agree with the dominant
    # direction should count toward the reliability component.
    result = compute_trade_quality(
        probability=probability,
        confidence_pct=80.0,
        department_votes=department_votes,
        department_reliability={"technical": 0.9, "correlation": 0.1},
    )
    only_agreeing = compute_trade_quality(
        probability=probability,
        confidence_pct=80.0,
        department_votes={"technical": _vote(0.8, 0.2)},
        department_reliability={"technical": 0.9},
    )

    assert result.score == only_agreeing.score


def test_books_confluence_adds_to_the_score_and_is_clamped() -> None:
    probability = ProbabilityEstimate(
        bullish_probability=0.6, bearish_probability=0.4, neutral_probability=0.0
    )
    department_votes = {"technical": _vote(0.6, 0.4)}

    without_books = compute_trade_quality(
        probability=probability,
        confidence_pct=70.0,
        department_votes=department_votes,
        books_confluence=0.0,
    )
    with_books = compute_trade_quality(
        probability=probability,
        confidence_pct=70.0,
        department_votes=department_votes,
        books_confluence=1.0,
    )
    over_range = compute_trade_quality(
        probability=probability,
        confidence_pct=70.0,
        department_votes=department_votes,
        books_confluence=5.0,
    )

    assert with_books.score > without_books.score
    assert with_books.score == over_range.score
    assert any("books_support" in reason for reason in with_books.reasoning)


def test_risk_score_reflects_the_risk_engines_own_confidence_tiers() -> None:
    probability = ProbabilityEstimate(
        bullish_probability=0.9, bearish_probability=0.1, neutral_probability=0.0
    )
    department_votes = {"technical": _vote(0.9, 0.1)}

    institutional = compute_trade_quality(
        probability=probability, confidence_pct=90.0, department_votes=department_votes
    )
    reject_tier = compute_trade_quality(
        probability=probability, confidence_pct=10.0, department_votes=department_votes
    )

    assert institutional.risk_score == 100.0
    assert reject_tier.risk_score == 0.0
