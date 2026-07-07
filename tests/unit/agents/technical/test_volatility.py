"""Unit tests for `VolatilityAgent`."""

from __future__ import annotations

import pytest

from src.agents.technical.volatility import VolatilityAgent, average_true_range, true_range
from tests.unit.agents.technical._helpers import make_candle

pytestmark = pytest.mark.unit


def _flat_close_candles(ranges: list[float]) -> list:
    """Build candles with a constant close (~100) and a controlled high-low range per bar."""
    candles = []
    for index, half_range in enumerate(ranges):
        candles.append(
            make_candle(
                index, open_=100.0, high=100.0 + half_range, low=100.0 - half_range, close=100.0
            )
        )
    return candles


def test_true_range_uses_widest_of_three_measures() -> None:
    previous = make_candle(0, open_=100, high=101, low=99, close=100)
    current = make_candle(1, open_=100, high=103, low=98, close=101)

    assert true_range(current, previous) == 5.0  # high(103) - low(98)


def test_average_true_range_returns_none_with_insufficient_candles() -> None:
    candles = _flat_close_candles([1.0, 1.0])

    assert average_true_range(candles, period=14) is None


def test_analyze_reports_unknown_with_insufficient_candles() -> None:
    candles = _flat_close_candles([1.0] * 3)

    report = VolatilityAgent(period=14).analyze(candles)

    assert report.bias == "neutral"
    assert report.confidence == 0.0
    assert report.unknowns


def test_analyze_detects_volatility_expansion() -> None:
    # 20 tight bars (range=1, i.e. TR~=2), then 5 wide bars (range=10, TR~=20).
    ranges = [1.0] * 20 + [10.0] * 5
    candles = _flat_close_candles(ranges)

    report = VolatilityAgent(period=5, comparison_period=20).analyze(candles)

    assert report.bias == "neutral"
    assert report.metrics["atr_ratio"] > 1.3
    assert any("expansion" in note for note in report.supporting_evidence)


def test_analyze_detects_volatility_compression() -> None:
    # 20 wide bars, then 5 tight bars.
    ranges = [10.0] * 20 + [1.0] * 5
    candles = _flat_close_candles(ranges)

    report = VolatilityAgent(period=5, comparison_period=20).analyze(candles)

    assert report.metrics["atr_ratio"] < 0.7
    assert any("compression" in note for note in report.supporting_evidence)


def test_analyze_reports_stable_volatility() -> None:
    ranges = [2.0] * 30

    report = VolatilityAgent(period=5, comparison_period=20).analyze(_flat_close_candles(ranges))

    assert any("stable" in note for note in report.opposing_evidence)
