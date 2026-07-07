"""Unit tests for cross-department confidence aggregation."""

from __future__ import annotations

import pytest

from src.engines.statistics_engine.confidence import ConfidenceInput, compute_overall_confidence

pytestmark = pytest.mark.unit


def test_returns_zero_for_no_inputs() -> None:
    assert compute_overall_confidence([]) == 0.0


def test_returns_zero_when_every_reliability_is_zero() -> None:
    inputs = [
        ConfidenceInput(name="technical", confidence=0.9, historical_reliability=0.0),
        ConfidenceInput(name="macro", confidence=0.8, historical_reliability=0.0),
    ]

    assert compute_overall_confidence(inputs) == 0.0


def test_averages_equal_reliability_inputs() -> None:
    inputs = [
        ConfidenceInput(name="technical", confidence=0.8),
        ConfidenceInput(name="macro", confidence=0.6),
    ]

    assert compute_overall_confidence(inputs) == pytest.approx(0.7)


def test_higher_reliability_input_dominates() -> None:
    inputs = [
        ConfidenceInput(name="technical", confidence=0.9, historical_reliability=1.0),
        ConfidenceInput(name="macro", confidence=0.1, historical_reliability=0.01),
    ]

    assert compute_overall_confidence(inputs) > 0.85
