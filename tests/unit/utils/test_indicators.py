"""Unit tests for `src.utils.indicators`."""

from __future__ import annotations

import pytest

from src.utils.indicators import (
    average_directional_index,
    exponential_moving_average,
    macd,
    rate_of_change,
    relative_strength_index,
    stochastic_oscillator,
)
from tests.unit.agents.technical._helpers import make_series

pytestmark = pytest.mark.unit


def test_ema_returns_none_with_insufficient_values() -> None:
    assert exponential_moving_average([1.0, 2.0], period=5) is None


def test_ema_seed_is_simple_average_of_first_period() -> None:
    result = exponential_moving_average([10.0, 20.0, 30.0], period=3)

    assert result is not None
    assert result[0] == pytest.approx(20.0)


def test_ema_tracks_a_steady_uptrend_upward() -> None:
    values = [100.0 + i for i in range(30)]

    result = exponential_moving_average(values, period=10)

    assert result is not None
    assert result[-1] > result[0]


def test_rsi_returns_none_with_insufficient_values() -> None:
    assert relative_strength_index([1.0, 2.0, 3.0], period=14) is None


def test_rsi_is_100_when_there_are_no_losses() -> None:
    values = [100.0 + i for i in range(20)]  # strictly increasing

    rsi = relative_strength_index(values, period=14)

    assert rsi == pytest.approx(100.0)


def test_rsi_is_0_when_there_are_no_gains() -> None:
    values = [100.0 - i for i in range(20)]  # strictly decreasing

    rsi = relative_strength_index(values, period=14)

    assert rsi == pytest.approx(0.0)


def test_rsi_is_near_50_for_a_flat_alternating_series() -> None:
    values = [
        100.0,
        101.0,
        100.0,
        101.0,
        100.0,
        101.0,
        100.0,
        101.0,
        100.0,
        101.0,
        100.0,
        101.0,
        100.0,
        101.0,
        100.0,
    ]

    rsi = relative_strength_index(values, period=14)

    assert rsi is not None
    assert 40.0 < rsi < 60.0


def test_macd_returns_none_with_insufficient_values() -> None:
    assert macd([1.0] * 10, fast_period=12, slow_period=26, signal_period=9) is None


def test_macd_returns_none_when_not_enough_data_for_the_signal_line() -> None:
    # Just enough for the fast/slow EMAs, but not enough resulting MACD
    # line values to seed the signal line's own EMA.
    values = [100.0 + i for i in range(6)]

    assert macd(values, fast_period=2, slow_period=5, signal_period=9) is None


def test_macd_histogram_is_positive_in_a_strong_uptrend() -> None:
    values = [100.0 + i * 0.5 for i in range(60)]

    result = macd(values, fast_period=12, slow_period=26, signal_period=9)

    assert result is not None
    assert result.macd_line > 0
    assert result.histogram == pytest.approx(result.macd_line - result.signal_line)


def test_macd_histogram_is_negative_in_a_strong_downtrend() -> None:
    values = [200.0 - i * 0.5 for i in range(60)]

    result = macd(values, fast_period=12, slow_period=26, signal_period=9)

    assert result is not None
    assert result.macd_line < 0


def test_roc_returns_none_with_insufficient_values() -> None:
    assert rate_of_change([1.0, 2.0], period=12) is None


def test_roc_is_positive_percentage_change() -> None:
    values = [100.0] * 12 + [110.0]

    roc = rate_of_change(values, period=12)

    assert roc == pytest.approx(10.0)


def test_roc_is_negative_for_a_decline() -> None:
    values = [100.0] * 12 + [90.0]

    roc = rate_of_change(values, period=12)

    assert roc == pytest.approx(-10.0)


def test_roc_returns_none_when_reference_price_is_zero() -> None:
    values = [0.0] * 12 + [10.0]

    assert rate_of_change(values, period=12) is None


def test_stochastic_returns_none_with_insufficient_candles() -> None:
    candles = make_series([100.0, 101.0])

    assert stochastic_oscillator(candles, k_period=14, d_period=3) is None


def test_stochastic_is_100_when_closing_at_the_period_high() -> None:
    closes = [100.0 + i for i in range(20)]  # strictly increasing, closes at the high each bar
    candles = make_series(closes, spread=0.0)

    result = stochastic_oscillator(candles, k_period=14, d_period=3)

    assert result is not None
    percent_k, percent_d = result
    assert percent_k == pytest.approx(100.0)
    assert percent_d == pytest.approx(100.0)


def test_stochastic_reports_neutral_50_when_the_period_range_is_flat() -> None:
    # Every candle in the window has the exact same high/low/close --
    # a zero-range window, which cannot be normalized to a %K position.
    candles = make_series([100.0] * 20, spread=0.0)

    result = stochastic_oscillator(candles, k_period=14, d_period=3)

    assert result is not None
    percent_k, percent_d = result
    assert percent_k == pytest.approx(50.0)
    assert percent_d == pytest.approx(50.0)


def test_adx_returns_none_with_insufficient_candles() -> None:
    candles = make_series([100.0, 101.0, 102.0])

    assert average_directional_index(candles, period=14) is None


def test_adx_is_high_for_a_strong_sustained_trend() -> None:
    closes = [100.0 + i * 2.0 for i in range(40)]
    candles = make_series(closes, spread=0.2)

    adx = average_directional_index(candles, period=14)

    assert adx is not None
    assert adx > 30.0


def test_adx_is_low_for_a_flat_choppy_market() -> None:
    closes = [100.0, 100.5, 99.5, 100.2, 99.8, 100.3, 99.7] * 6
    candles = make_series(closes, spread=0.1)

    adx = average_directional_index(candles, period=14)

    assert adx is not None
    assert adx < 30.0


def test_adx_handles_a_completely_flat_zero_range_series() -> None:
    # Every bar has zero true range (open == high == low == close ==
    # previous close), which would otherwise divide by zero.
    candles = make_series([100.0] * 40, spread=0.0)

    adx = average_directional_index(candles, period=14)

    assert adx == pytest.approx(0.0)
