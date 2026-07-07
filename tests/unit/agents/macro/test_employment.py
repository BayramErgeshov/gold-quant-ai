"""Unit tests for `EmploymentAgent`."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from src.agents.macro.employment import EmploymentAgent
from src.core.macro_analysis.agent import MacroObservation

pytestmark = pytest.mark.unit


def _observations(values: list[float]) -> list[MacroObservation]:
    base = date(2026, 1, 1)
    return [
        MacroObservation(observed_on=base + timedelta(days=30 * index), value=value)
        for index, value in enumerate(values)
    ]


def test_rising_unemployment_is_bullish_for_gold() -> None:
    report = EmploymentAgent().analyze(_observations([4.0, 4.5, 5.0, 5.5, 6.0]))

    assert report.bias == "bullish"
    assert report.confidence > 0.0


def test_falling_unemployment_is_bearish_for_gold() -> None:
    report = EmploymentAgent().analyze(_observations([6.0, 5.5, 5.0, 4.5, 4.0]))

    assert report.bias == "bearish"


def test_stable_unemployment_is_neutral() -> None:
    report = EmploymentAgent().analyze(_observations([4.0, 4.0, 4.1, 4.0]))

    assert report.bias == "neutral"
