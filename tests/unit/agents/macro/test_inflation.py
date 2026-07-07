"""Unit tests for `InflationAgent`."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from src.agents.macro.inflation import InflationAgent
from src.core.macro_analysis.agent import MacroObservation

pytestmark = pytest.mark.unit


def _observations(values: list[float]) -> list[MacroObservation]:
    base = date(2026, 1, 1)
    return [
        MacroObservation(observed_on=base + timedelta(days=30 * index), value=value)
        for index, value in enumerate(values)
    ]


def test_accelerating_inflation_is_bullish_for_gold() -> None:
    report = InflationAgent().analyze(_observations([100.0, 101.0, 102.5, 104.5, 107.0]))

    assert report.bias == "bullish"
    assert report.confidence > 0.0


def test_decelerating_inflation_is_bearish_for_gold() -> None:
    report = InflationAgent().analyze(_observations([107.0, 104.5, 102.5, 101.0, 100.0]))

    assert report.bias == "bearish"


def test_stable_inflation_is_neutral() -> None:
    report = InflationAgent().analyze(_observations([100.0, 100.1, 100.0, 100.1]))

    assert report.bias == "neutral"
