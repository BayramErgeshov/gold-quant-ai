"""Unit tests for Scalping Engine microstructure analysis."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from src.engines.scalping_engine.microstructure import (
    classify_session,
    compute_spread_change_pct,
    detect_breakout_failure,
    detect_micro_pullback,
    detect_momentum_burst,
)
from src.models.candle import Candle

pytestmark = pytest.mark.unit

_BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


def _candle(offset: int, *, open_: float, high: float, low: float, close: float) -> Candle:
    return Candle(
        symbol_id=uuid.uuid4(),
        timeframe="M1",
        timestamp=_BASE_TIME + timedelta(minutes=offset),
        open=open_,
        high=high,
        low=low,
        close=close,
        source="test_fixture",
    )


def _flat_baseline(count: int, *, price: float = 100.0) -> list[Candle]:
    return [
        _candle(i, open_=price, high=price + 0.1, low=price - 0.1, close=price)
        for i in range(count)
    ]


def test_detect_momentum_burst_returns_none_with_insufficient_history() -> None:
    assert detect_momentum_burst(_flat_baseline(2)) is None


def test_detect_momentum_burst_detects_a_strong_bullish_move() -> None:
    baseline = _flat_baseline(16, price=100.0)
    burst = [
        _candle(16, open_=100.0, high=102.0, low=99.9, close=101.5),
        _candle(17, open_=101.5, high=103.5, low=101.4, close=103.0),
        _candle(18, open_=103.0, high=105.5, low=102.9, close=105.0),
    ]

    result = detect_momentum_burst(baseline + burst)

    assert result is not None
    assert result.direction == "bullish"
    assert result.move_pct > 0


def test_detect_momentum_burst_ignores_ordinary_movement() -> None:
    baseline = _flat_baseline(20, price=100.0)

    assert detect_momentum_burst(baseline) is None


def test_detect_breakout_failure_returns_none_with_insufficient_history() -> None:
    assert detect_breakout_failure(_flat_baseline(3), lookback=10) is None


def test_detect_breakout_failure_detects_a_failed_breakout_high() -> None:
    prior = [_candle(i, open_=100.0, high=101.0, low=99.0, close=100.0) for i in range(10)]
    # Wicks above the recent high (101.0) but closes back below it.
    failed = _candle(10, open_=100.5, high=102.0, low=100.4, close=100.8)

    result = detect_breakout_failure(prior + [failed], lookback=10)

    assert result is not None
    assert result.direction == "bearish"
    assert result.broken_level == 101.0


def test_detect_breakout_failure_detects_a_failed_breakdown_low() -> None:
    prior = [_candle(i, open_=100.0, high=101.0, low=99.0, close=100.0) for i in range(10)]
    failed = _candle(10, open_=99.5, high=99.6, low=98.0, close=99.2)

    result = detect_breakout_failure(prior + [failed], lookback=10)

    assert result is not None
    assert result.direction == "bullish"
    assert result.broken_level == 99.0


def test_detect_breakout_failure_ignores_a_clean_breakout() -> None:
    prior = [_candle(i, open_=100.0, high=101.0, low=99.0, close=100.0) for i in range(10)]
    clean_breakout = _candle(10, open_=100.5, high=102.0, low=100.4, close=101.8)

    assert detect_breakout_failure(prior + [clean_breakout], lookback=10) is None


def test_detect_micro_pullback_returns_none_with_insufficient_history() -> None:
    assert detect_micro_pullback(_flat_baseline(1)) is None


def test_detect_micro_pullback_detects_a_shallow_bullish_retrace() -> None:
    baseline = _flat_baseline(15, price=100.0)
    impulse = _candle(15, open_=100.0, high=105.5, low=99.9, close=105.0)
    pullback = _candle(16, open_=105.0, high=105.1, low=104.0, close=104.2)

    result = detect_micro_pullback(baseline + [impulse, pullback])

    assert result is not None
    assert result.direction == "bullish"
    assert 0.0 < result.retrace_pct <= 0.4


def test_detect_micro_pullback_rejects_a_deep_retrace() -> None:
    baseline = _flat_baseline(15, price=100.0)
    impulse = _candle(15, open_=100.0, high=105.5, low=99.9, close=105.0)
    deep_pullback = _candle(16, open_=105.0, high=105.1, low=99.5, close=100.0)

    assert detect_micro_pullback(baseline + [impulse, deep_pullback]) is None


def test_detect_micro_pullback_rejects_a_small_impulse() -> None:
    baseline = _flat_baseline(15, price=100.0)
    small_impulse = _candle(15, open_=100.0, high=100.2, low=99.9, close=100.1)
    small_pullback = _candle(16, open_=100.1, high=100.15, low=100.0, close=100.05)

    assert detect_micro_pullback(baseline + [small_impulse, small_pullback]) is None


def test_detect_micro_pullback_rejects_continuation_in_the_same_direction() -> None:
    baseline = _flat_baseline(15, price=100.0)
    impulse = _candle(15, open_=100.0, high=105.5, low=99.9, close=105.0)
    # Keeps moving up instead of pulling back -> not a pullback at all.
    continuation = _candle(16, open_=105.0, high=106.5, low=104.9, close=106.0)

    assert detect_micro_pullback(baseline + [impulse, continuation]) is None


def test_detect_momentum_burst_returns_none_with_a_zero_start_price() -> None:
    baseline = _flat_baseline(16, price=100.0)
    degenerate = [
        _candle(16, open_=0.0, high=1.0, low=0.0, close=0.5),
        _candle(17, open_=0.5, high=2.0, low=0.4, close=1.8),
        _candle(18, open_=1.8, high=3.5, low=1.7, close=3.2),
    ]

    assert detect_momentum_burst(baseline + degenerate) is None


@pytest.mark.parametrize(
    ("hour", "expected"),
    [
        (2, "asia"),
        (23, "asia"),
        (8, "london"),
        (11, "london"),
        (13, "london_new_york_overlap"),
        (18, "new_york"),
        (21, "closed"),
        (22, "closed"),
    ],
)
def test_classify_session(hour: int, expected: str) -> None:
    timestamp = datetime(2026, 1, 1, hour, tzinfo=UTC)

    assert classify_session(timestamp) == expected


def test_classify_session_handles_naive_datetime_as_utc() -> None:
    naive = datetime(2026, 1, 1, 13)

    assert classify_session(naive) == "london_new_york_overlap"


def test_compute_spread_change_pct_with_insufficient_data() -> None:
    assert compute_spread_change_pct([]) == 0.0
    assert compute_spread_change_pct([1.0]) == 0.0


def test_compute_spread_change_pct_detects_widening() -> None:
    result = compute_spread_change_pct([10.0, 10.0, 10.0, 20.0])

    assert result == pytest.approx(100.0)


def test_compute_spread_change_pct_zero_baseline_is_zero() -> None:
    assert compute_spread_change_pct([0.0, 0.0, 5.0]) == 0.0
