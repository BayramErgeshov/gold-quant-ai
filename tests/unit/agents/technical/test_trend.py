"""Unit tests for `TrendAgent`."""

from __future__ import annotations

import math

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


def test_analyze_omits_longer_ema_and_adx_metrics_with_too_little_history() -> None:
    # 20 candles: enough for the slope-based bias and EMA20 itself, but
    # far short of the 200 EMA200 needs or the 29 ADX needs.
    candles = make_series([100.0 + index * 3 for index in range(20)])

    report = TrendAgent().analyze(candles)

    assert report.bias == "bullish"
    assert "ema_50" not in report.metrics
    assert "ema_100" not in report.metrics
    assert "ema_200" not in report.metrics
    assert "adx" not in report.metrics


def test_analyze_confirms_bullish_trend_with_a_stacked_ema_alignment_and_strong_adx() -> None:
    # A long, strong, near-linear uptrend: EMA20 > EMA50 > EMA100 > EMA200
    # and a high ADX both confirm the slope-based bullish bias.
    closes = [100.0 + index * 0.8 for index in range(250)]
    candles = make_series(closes, spread=0.3)

    report = TrendAgent().analyze(candles)

    assert report.bias == "bullish"
    assert report.metrics["ema_20"] > report.metrics["ema_50"]
    assert report.metrics["ema_50"] > report.metrics["ema_100"]
    assert report.metrics["ema_100"] > report.metrics["ema_200"]
    assert report.metrics["adx"] >= 25.0
    assert any("fully stacked" in note for note in report.supporting_evidence)
    assert any("ADX" in note and "confirms" in note for note in report.supporting_evidence)


def test_analyze_flags_a_contradicting_ema_stack_as_opposing_evidence() -> None:
    # A long, steady uptrend anchors EMA100/200 well below EMA20/50, then
    # a sharp recent decline flips the EMA stack fully bearish while the
    # overall regression slope (dominated by the long uptrend) still
    # reads bullish -- the bias stays bullish, but the EMA stack disagrees.
    closes = [100.0 + index * 1.0 for index in range(200)] + [
        300.0 - index * 6.0 for index in range(1, 51)
    ]
    candles = make_series(closes, spread=0.3)

    report = TrendAgent().analyze(candles)

    assert report.bias == "bullish"
    assert report.metrics["ema_20"] < report.metrics["ema_50"]
    assert report.metrics["ema_50"] < report.metrics["ema_100"]
    assert report.metrics["ema_100"] < report.metrics["ema_200"]
    assert any("stacked against" in note for note in report.opposing_evidence)


def test_analyze_flags_a_weak_adx_as_opposing_evidence() -> None:
    # A choppy, noisy series with only a slight net uptrend: the EMA
    # stack still confirms bullish, but ADX reads weak.
    closes = [100.0 + index * 0.1 + 3.0 * math.sin(index * 0.9) for index in range(250)]
    candles = make_series(closes, spread=0.3)

    report = TrendAgent().analyze(candles)

    assert report.bias == "bullish"
    assert report.metrics["adx"] < 25.0
    assert any("weak or absent" in note for note in report.opposing_evidence)
