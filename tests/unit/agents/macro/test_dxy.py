"""Unit tests for `DollarIndexAgent`."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from src.agents.macro.dxy import DollarIndexAgent
from src.core.macro_analysis.agent import MacroObservation

pytestmark = pytest.mark.unit


def _observations(values: list[float]) -> list[MacroObservation]:
    base = date(2026, 1, 1)
    return [
        MacroObservation(observed_on=base + timedelta(days=index), value=value)
        for index, value in enumerate(values)
    ]


def test_strengthening_dollar_is_bearish_for_gold() -> None:
    report = DollarIndexAgent().analyze(_observations([100.0, 101.0, 102.0, 103.0, 104.0]))

    assert report.bias == "bearish"
    assert report.confidence > 0.0


def test_weakening_dollar_is_bullish_for_gold() -> None:
    report = DollarIndexAgent().analyze(_observations([104.0, 103.0, 102.0, 101.0, 100.0]))

    assert report.bias == "bullish"


def test_stable_dollar_is_neutral() -> None:
    report = DollarIndexAgent().analyze(_observations([100.0, 100.1, 100.0, 100.1]))

    assert report.bias == "neutral"
