"""Unit tests for `src.core.technical_analysis.swings`."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from src.core.technical_analysis.swings import find_swing_points
from src.models.candle import Candle

pytestmark = pytest.mark.unit

_SYMBOL_ID = uuid.uuid4()
_BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


def _candle(index: int, *, high: float, low: float) -> Candle:
    return Candle(
        symbol_id=_SYMBOL_ID,
        timeframe="H1",
        timestamp=_BASE_TIME + timedelta(hours=index),
        open=(high + low) / 2,
        high=high,
        low=low,
        close=(high + low) / 2,
        source="test_fixture",
    )


def test_find_swing_points_returns_empty_for_too_short_series() -> None:
    candles = [_candle(0, high=100, low=99)]

    assert find_swing_points(candles, lookaround=2) == []


def test_find_swing_points_detects_a_clear_swing_high() -> None:
    candles = [
        _candle(0, high=100, low=95),
        _candle(1, high=105, low=98),
        _candle(2, high=120, low=110),  # the peak
        _candle(3, high=104, low=97),
        _candle(4, high=101, low=96),
    ]

    swings = find_swing_points(candles, lookaround=2)

    assert len(swings) == 1
    assert swings[0].kind == "high"
    assert swings[0].index == 2


def test_find_swing_points_detects_a_clear_swing_low() -> None:
    candles = [
        _candle(0, high=100, low=90),
        _candle(1, high=98, low=85),
        _candle(2, high=97, low=70),  # the trough
        _candle(3, high=99, low=84),
        _candle(4, high=100, low=88),
    ]

    swings = find_swing_points(candles, lookaround=2)

    assert len(swings) == 1
    assert swings[0].kind == "low"
    assert swings[0].index == 2


def test_find_swing_points_detects_multiple_points_in_order() -> None:
    candles = [
        _candle(0, high=100, low=90),
        _candle(1, high=98, low=85),
        _candle(2, high=97, low=70),  # trough
        _candle(3, high=99, low=84),
        _candle(4, high=120, low=100),  # peak
        _candle(5, high=99, low=84),
        _candle(6, high=97, low=71),  # trough
        _candle(7, high=98, low=85),
        _candle(8, high=100, low=90),
    ]

    swings = find_swing_points(candles, lookaround=2)

    assert [swing.index for swing in swings] == [2, 4, 6]
    assert [swing.kind for swing in swings] == ["low", "high", "low"]
