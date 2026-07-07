"""Unit tests for hypothesis generation."""

from __future__ import annotations

import pytest

from src.engines.learning_engine.factor_analysis import TradeFactor
from src.engines.learning_engine.hypothesis import generate_hypotheses_from_factors

pytestmark = pytest.mark.unit


def test_no_hypothesis_below_minimum_occurrences() -> None:
    factors = [TradeFactor(name="stop_too_close", detail="x") for _ in range(2)]

    assert generate_hypotheses_from_factors(factors, min_occurrences=3) == []


def test_generates_hypothesis_at_minimum_occurrences() -> None:
    factors = [TradeFactor(name="stop_too_close", detail="x") for _ in range(3)]

    hypotheses = generate_hypotheses_from_factors(factors, min_occurrences=3)

    assert len(hypotheses) == 1
    assert "stop_too_close" in hypotheses[0].question
    assert hypotheses[0].priority == "P2"


def test_generates_high_priority_hypothesis_for_strongly_recurring_factor() -> None:
    factors = [TradeFactor(name="stop_too_close", detail="x") for _ in range(6)]

    hypotheses = generate_hypotheses_from_factors(factors, min_occurrences=3)

    assert hypotheses[0].priority == "P1"


def test_orders_hypotheses_by_frequency_descending() -> None:
    factors = [TradeFactor(name="frequent", detail="x") for _ in range(5)] + [
        TradeFactor(name="less_frequent", detail="y") for _ in range(3)
    ]

    hypotheses = generate_hypotheses_from_factors(factors, min_occurrences=3)

    assert len(hypotheses) == 2
    assert "'frequent'" in hypotheses[0].question
    assert "'less_frequent'" in hypotheses[1].question


def test_returns_empty_for_no_factors() -> None:
    assert generate_hypotheses_from_factors([]) == []
