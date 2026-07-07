"""Unit tests for `BondYieldAgent`."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from src.agents.macro.bond_yield import BondYieldAgent
from src.core.macro_analysis.agent import MacroObservation

pytestmark = pytest.mark.unit


def _observations(values: list[float]) -> list[MacroObservation]:
    base = date(2026, 1, 1)
    return [
        MacroObservation(observed_on=base + timedelta(days=index), value=value)
        for index, value in enumerate(values)
    ]


def test_rising_yields_are_bearish_for_gold() -> None:
    report = BondYieldAgent().analyze(_observations([3.5, 3.8, 4.1, 4.4, 4.7]))

    assert report.bias == "bearish"
    assert report.confidence > 0.0


def test_falling_yields_are_bullish_for_gold() -> None:
    report = BondYieldAgent().analyze(_observations([4.7, 4.4, 4.1, 3.8, 3.5]))

    assert report.bias == "bullish"


def test_stable_yields_are_neutral() -> None:
    report = BondYieldAgent().analyze(_observations([4.0, 4.0, 4.05, 4.0]))

    assert report.bias == "neutral"
