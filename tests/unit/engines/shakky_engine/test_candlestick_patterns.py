"""Unit tests for Shakky's five allowed candlestick patterns."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from src.engines.shakky_engine.candlestick_patterns import (
    classify_hammer_or_hanging_man,
    detect_doji_signal,
    detect_engulfing_signal,
    detect_pin_bar_signal,
)
from src.models.candle import Candle

pytestmark = pytest.mark.unit

_SYMBOL_ID = uuid.uuid4()
_BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


def _candle(offset: int, *, open_: float, high: float, low: float, close: float) -> Candle:
    return Candle(
        symbol_id=_SYMBOL_ID,
        timeframe="M5",
        timestamp=_BASE_TIME + timedelta(minutes=5 * offset),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=100.0,
        source="test_fixture",
    )


def test_detect_pin_bar_signal_bullish() -> None:
    candle = _candle(0, open_=2000.0, high=2000.5, low=1995.0, close=2000.2)

    signal = detect_pin_bar_signal(candle)

    assert signal is not None
    assert signal.direction == "buy"


def test_detect_pin_bar_signal_bearish() -> None:
    candle = _candle(0, open_=2000.0, high=2005.0, low=1999.5, close=1999.8)

    signal = detect_pin_bar_signal(candle)

    assert signal is not None
    assert signal.direction == "sell"


def test_detect_pin_bar_signal_none_for_ordinary_candle() -> None:
    candle = _candle(0, open_=2000.0, high=2001.0, low=1999.0, close=2000.5)

    assert detect_pin_bar_signal(candle) is None


def test_detect_engulfing_signal_bullish() -> None:
    previous = _candle(0, open_=2001.0, high=2001.5, low=1999.0, close=1999.5)
    current = _candle(1, open_=1999.0, high=2002.0, low=1998.5, close=2001.8)

    signal = detect_engulfing_signal(previous, current)

    assert signal is not None
    assert signal.direction == "buy"


def test_detect_engulfing_signal_none_when_same_direction() -> None:
    previous = _candle(0, open_=1999.0, high=2000.5, low=1998.5, close=2000.0)
    current = _candle(1, open_=2000.0, high=2001.5, low=1999.5, close=2001.0)

    assert detect_engulfing_signal(previous, current) is None


def test_detect_doji_signal_has_no_direction() -> None:
    candle = _candle(0, open_=2000.0, high=2001.0, low=1999.0, close=2000.02)

    signal = detect_doji_signal(candle)

    assert signal is not None
    assert signal.direction is None


def test_detect_doji_signal_none_for_a_real_body() -> None:
    candle = _candle(0, open_=2000.0, high=2002.0, low=1999.5, close=2001.8)

    assert detect_doji_signal(candle) is None


def _downtrend_then_pin_bar() -> list[Candle]:
    down = [
        _candle(i, open_=2010.0 - i, high=2010.5 - i, low=2009.0 - i, close=2009.5 - i)
        for i in range(5)
    ]
    pin_bar = _candle(5, open_=2005.5, high=2006.0, low=2000.0, close=2005.8)
    return down + [pin_bar]


def _uptrend_then_pin_bar() -> list[Candle]:
    up = [
        _candle(i, open_=2000.0 + i, high=2001.0 + i, low=1999.5 + i, close=2000.5 + i)
        for i in range(5)
    ]
    pin_bar = _candle(5, open_=2004.5, high=2005.0, low=1999.0, close=2004.8)
    return up + [pin_bar]


def test_classify_hammer_after_a_downswing() -> None:
    signal = classify_hammer_or_hanging_man(_downtrend_then_pin_bar())

    assert signal is not None
    assert signal.name == "hammer"
    assert signal.direction == "buy"


def test_classify_hanging_man_after_an_upswing() -> None:
    signal = classify_hammer_or_hanging_man(_uptrend_then_pin_bar())

    assert signal is not None
    assert signal.name == "hanging_man"
    assert signal.direction == "sell"


def test_classify_hammer_or_hanging_man_none_without_enough_history() -> None:
    assert classify_hammer_or_hanging_man(_downtrend_then_pin_bar()[-2:]) is None


def test_classify_hammer_or_hanging_man_none_for_a_bearish_shaped_candle() -> None:
    # A shooting-star-shaped candle (long upper wick) is not part of the
    # required Hammer/Hanging Man pair.
    candles = _downtrend_then_pin_bar()[:-1] + [
        _candle(5, open_=2005.0, high=2010.0, low=2004.8, close=2005.2)
    ]

    assert classify_hammer_or_hanging_man(candles) is None
