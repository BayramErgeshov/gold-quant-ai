"""Unit tests for `InterestRateAgent`."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from src.agents.macro.interest_rate import InterestRateAgent
from src.core.macro_analysis.agent import MacroObservation

pytestmark = pytest.mark.unit


def _observations(values: list[float]) -> list[MacroObservation]:
    base = date(2026, 1, 1)
    return [
        MacroObservation(observed_on=base + timedelta(days=30 * index), value=value)
        for index, value in enumerate(values)
    ]


def test_rising_rate_is_bearish_for_gold() -> None:
    report = InterestRateAgent().analyze(_observations([1.0, 2.0, 3.0, 4.0, 5.0]))

    assert report.bias == "bearish"
    assert report.confidence > 0.0


def test_falling_rate_is_bullish_for_gold() -> None:
    report = InterestRateAgent().analyze(_observations([5.0, 4.0, 3.0, 2.0, 1.0]))

    assert report.bias == "bullish"


def test_flat_rate_is_neutral() -> None:
    report = InterestRateAgent().analyze(_observations([2.0, 2.0, 2.0, 2.0]))

    assert report.bias == "neutral"
