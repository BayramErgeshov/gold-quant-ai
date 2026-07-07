"""Unit tests for `PriceActionAgent` and its pattern detectors."""

from __future__ import annotations

import pytest

from src.agents.technical.price_action import (
    PriceActionAgent,
    detect_doji,
    detect_engulfing,
    detect_inside_bar,
    detect_marubozu,
    detect_outside_bar,
    detect_pin_bar,
)
from tests.unit.agents.technical._helpers import make_candle

pytestmark = pytest.mark.unit


def test_detect_doji_identifies_tiny_body() -> None:
    candle = make_candle(0, open_=100.0, high=105.0, low=95.0, close=100.2)

    pattern = detect_doji(candle)

    assert pattern is not None
    assert pattern.name == "doji"
    assert pattern.bias == "neutral"


def test_detect_doji_returns_none_for_large_body() -> None:
    candle = make_candle(0, open_=100.0, high=105.0, low=95.0, close=104.0)

    assert detect_doji(candle) is None


def test_detect_marubozu_identifies_bullish_dominant_body() -> None:
    candle = make_candle(0, open_=100.0, high=110.0, low=99.5, close=109.5)

    pattern = detect_marubozu(candle)

    assert pattern is not None
    assert pattern.bias == "bullish"


def test_detect_marubozu_identifies_bearish_dominant_body() -> None:
    candle = make_candle(0, open_=110.0, high=110.5, low=100.0, close=100.5)

    pattern = detect_marubozu(candle)

    assert pattern is not None
    assert pattern.bias == "bearish"


def test_detect_pin_bar_identifies_hammer() -> None:
    # Long lower wick, small body near the top, negligible upper wick.
    candle = make_candle(0, open_=99.0, high=100.0, low=90.0, close=100.0)

    pattern = detect_pin_bar(candle)

    assert pattern is not None
    assert pattern.name == "hammer"
    assert pattern.bias == "bullish"


def test_detect_pin_bar_identifies_shooting_star() -> None:
    # Long upper wick, small body near the bottom, negligible lower wick.
    candle = make_candle(0, open_=100.0, high=110.0, low=99.5, close=100.0)

    pattern = detect_pin_bar(candle)

    assert pattern is not None
    assert pattern.name == "shooting_star"
    assert pattern.bias == "bearish"


def test_detect_pin_bar_returns_none_for_balanced_candle() -> None:
    candle = make_candle(0, open_=98.0, high=103.0, low=97.0, close=102.0)

    assert detect_pin_bar(candle) is None


def test_detect_engulfing_identifies_bullish_engulfing() -> None:
    previous = make_candle(0, open_=102.0, high=103.0, low=99.0, close=100.0)
    current = make_candle(1, open_=99.5, high=104.0, low=99.0, close=103.5)

    pattern = detect_engulfing(previous, current)

    assert pattern is not None
    assert pattern.name == "bullish_engulfing"


def test_detect_engulfing_identifies_bearish_engulfing() -> None:
    previous = make_candle(0, open_=100.0, high=103.0, low=99.0, close=102.0)
    current = make_candle(1, open_=103.0, high=104.0, low=98.0, close=99.0)

    pattern = detect_engulfing(previous, current)

    assert pattern is not None
    assert pattern.name == "bearish_engulfing"


def test_detect_engulfing_returns_none_for_same_direction_candles() -> None:
    previous = make_candle(0, open_=100.0, high=103.0, low=99.0, close=102.0)
    current = make_candle(1, open_=102.0, high=106.0, low=101.0, close=105.0)

    assert detect_engulfing(previous, current) is None


def test_detect_inside_bar() -> None:
    previous = make_candle(0, open_=100.0, high=105.0, low=95.0, close=102.0)
    current = make_candle(1, open_=101.0, high=103.0, low=98.0, close=100.0)

    pattern = detect_inside_bar(previous, current)

    assert pattern is not None
    assert pattern.name == "inside_bar"


def test_detect_outside_bar() -> None:
    previous = make_candle(0, open_=100.0, high=102.0, low=98.0, close=101.0)
    current = make_candle(1, open_=99.0, high=106.0, low=94.0, close=105.0)

    pattern = detect_outside_bar(previous, current)

    assert pattern is not None
    assert pattern.name == "outside_bar"


def test_analyze_reports_unknown_with_too_few_candles() -> None:
    candles = [make_candle(0, open_=100, high=101, low=99, close=100)]

    report = PriceActionAgent().analyze(candles)

    assert report.bias == "neutral"
    assert report.unknowns


def test_analyze_reports_bullish_for_hammer_pattern() -> None:
    candles = [
        make_candle(0, open_=105.0, high=106.0, low=104.0, close=104.5),
        make_candle(1, open_=99.0, high=100.0, low=90.0, close=100.0),
    ]

    report = PriceActionAgent().analyze(candles)

    assert report.bias == "bullish"
    assert report.confidence > 0.0


def test_analyze_reports_neutral_when_no_pattern_detected() -> None:
    candles = [
        make_candle(0, open_=100.0, high=103.0, low=97.0, close=101.0),
        make_candle(1, open_=101.0, high=104.0, low=99.0, close=102.0),
    ]

    report = PriceActionAgent().analyze(candles)

    assert report.bias == "neutral"


def test_detect_pin_bar_returns_none_for_zero_range_candle() -> None:
    candle = make_candle(0, open_=100.0, high=100.0, low=100.0, close=100.0)

    assert detect_pin_bar(candle) is None


def test_analyze_reports_bearish_for_bearish_engulfing_pattern() -> None:
    candles = [
        make_candle(0, open_=100.0, high=102.0, low=99.0, close=101.5),
        make_candle(1, open_=103.0, high=104.0, low=98.0, close=99.0),
    ]

    report = PriceActionAgent().analyze(candles)

    assert report.bias == "bearish"
    assert report.confidence > 0.0
    assert any("engulfing" in note.lower() for note in report.supporting_evidence)


def test_analyze_reports_neutral_when_patterns_conflict() -> None:
    # `current` is simultaneously a bullish hammer (by wick geometry) and
    # a bearish engulfing candle relative to `previous` -- a genuine
    # conflict between two directional patterns on the same candle.
    previous = make_candle(0, open_=100.05, high=100.6, low=100.0, close=100.45)
    current = make_candle(1, open_=100.5, high=101.0, low=85.0, close=100.0)

    report = PriceActionAgent().analyze([previous, current])

    assert report.bias == "neutral"
