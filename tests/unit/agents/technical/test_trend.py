"""Unit tests for `TrendAgent`."""

from __future__ import annotations

import pytest

from src.agents.technical.trend import TrendAgent
from tests.unit.agents.technical._helpers import make_series

pytestmark = pytest.mark.unit


def test_analyze_reports_neutral_with_too_few_candles() -> None:
    candles = make_series([100.0, 101.0])

    report = TrendAgent().analyze(candles)

    assert report.bias == "neutral"
    assert report.confidence == 0.0
    assert report.unknowns


def test_analyze_detects_bullish_trend() -> None:
    candles = make_series([100.0 + index * 3 for index in range(20)])

    report = TrendAgent().analyze(candles)

    assert report.bias == "bullish"
    assert report.confidence > 0.0
    assert report.metrics["slope_pct"] > 0
    assert report.metrics["trend_age_bars"] > 0


def test_analyze_detects_bearish_trend() -> None:
    candles = make_series([200.0 - index * 3 for index in range(20)])

    report = TrendAgent().analyze(candles)

    assert report.bias == "bearish"
    assert report.metrics["slope_pct"] < 0


def test_analyze_reports_neutral_for_flat_series() -> None:
    candles = make_series([100.0] * 20)

    report = TrendAgent().analyze(candles)

    assert report.bias == "neutral"
    assert report.confidence == 0.0


def test_analyze_detects_accelerating_trend() -> None:
    # Slow drift, then a sharp acceleration in the second half.
    closes = [100.0 + index * 0.5 for index in range(10)] + [
        105.0 + index * 5 for index in range(1, 11)
    ]

    report = TrendAgent().analyze(make_series(closes))

    assert report.bias == "bullish"
    assert any("accelerating" in note for note in report.supporting_evidence)


def test_analyze_detects_decelerating_trend() -> None:
    # Sharp move, then a slow drift in the second half (same direction,
    # much less steep) -- still trending overall, but decelerating.
    closes = [100.0 + index * 5 for index in range(10)] + [
        145.0 + index * 0.2 for index in range(1, 11)
    ]

    report = TrendAgent().analyze(make_series(closes))

    assert report.bias == "bullish"
    assert any("decelerating" in note for note in report.opposing_evidence)


def test_trend_age_stops_counting_at_a_pullback_candle() -> None:
    # Net uptrend, but with one pullback candle four bars from the end --
    # trend age should stop there rather than counting the whole series.
    closes = [100.0, 103.0, 106.0, 109.0, 112.0, 110.0, 113.0, 116.0, 119.0, 122.0]

    report = TrendAgent().analyze(make_series(closes))

    assert report.bias == "bullish"
    assert report.metrics["trend_age_bars"] == 4
