"""Shared technical indicator math (EMA, RSI, MACD, ROC, Stochastic, ADX).

Per CODING_STANDARDS.md ("never duplicate functionality"): every
Technical Department agent that needs one of these classical indicators
(Momentum Engine's RSI/MACD/ROC/Stochastic, Trend Engine's EMA/ADX)
imports it from here rather than re-deriving it. Every function returns
`None` when there is not enough data — never a fabricated value.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.models.candle import Candle


def exponential_moving_average(values: list[float], *, period: int) -> list[float] | None:
    """Compute the EMA series over `values`.

    Args:
        values: A price series, oldest first.
        period: The EMA period.

    Returns:
        One EMA value per input value from the point the seed average is
        available onward (length `len(values) - period + 1`), or None if
        fewer than `period` values are given.
    """
    if period <= 0 or len(values) < period:
        return None
    multiplier = 2.0 / (period + 1)
    seed = sum(values[:period]) / period
    ema_values = [seed]
    for value in values[period:]:
        ema_values.append((value - ema_values[-1]) * multiplier + ema_values[-1])
    return ema_values


def relative_strength_index_series(values: list[float], *, period: int = 14) -> list[float] | None:
    """Compute Wilder's RSI at every point once enough history exists.

    Args:
        values: A price series (typically closes), oldest first.
        period: The RSI lookback period.

    Returns:
        One RSI value (in [0, 100]) per input value from the point the
        seed average is available onward, or None if fewer than
        `period + 1` values are given.
    """
    if period <= 0 or len(values) < period + 1:
        return None
    changes = [values[i] - values[i - 1] for i in range(1, len(values))]
    gains = [max(change, 0.0) for change in changes]
    losses = [max(-change, 0.0) for change in changes]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    def _rsi_from_averages(gain: float, loss: float) -> float:
        if loss == 0:
            return 100.0
        return 100.0 - (100.0 / (1.0 + gain / loss))

    rsi_values = [_rsi_from_averages(avg_gain, avg_loss)]
    for gain, loss in zip(gains[period:], losses[period:], strict=True):
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        rsi_values.append(_rsi_from_averages(avg_gain, avg_loss))
    return rsi_values


def relative_strength_index(values: list[float], *, period: int = 14) -> float | None:
    """Compute the most recent Wilder's RSI value.

    Args:
        values: A price series (typically closes), oldest first.
        period: The RSI lookback period.

    Returns:
        RSI in [0, 100], or None if fewer than `period + 1` values are given.
    """
    series = relative_strength_index_series(values, period=period)
    return None if series is None else series[-1]


@dataclass(frozen=True, slots=True)
class MACDResult:
    """MACD line, signal line and histogram (most recent values)."""

    macd_line: float
    signal_line: float
    histogram: float


def macd(
    values: list[float], *, fast_period: int = 12, slow_period: int = 26, signal_period: int = 9
) -> MACDResult | None:
    """Compute the most recent MACD line/signal/histogram values.

    Args:
        values: A price series (typically closes), oldest first.
        fast_period: Fast EMA period.
        slow_period: Slow EMA period.
        signal_period: Signal line EMA period (applied to the MACD line).

    Returns:
        The most recent `MACDResult`, or None if there is not enough data.
    """
    fast_ema = exponential_moving_average(values, period=fast_period)
    slow_ema = exponential_moving_average(values, period=slow_period)
    if fast_ema is None or slow_ema is None:
        return None
    # Align both EMA series to the same trailing window (slow_ema is shorter).
    offset = len(fast_ema) - len(slow_ema)
    macd_line_series = [fast_ema[offset + i] - slow_ema[i] for i in range(len(slow_ema))]
    signal_series = exponential_moving_average(macd_line_series, period=signal_period)
    if signal_series is None:
        return None
    macd_line = macd_line_series[-1]
    signal_line = signal_series[-1]
    return MACDResult(
        macd_line=macd_line, signal_line=signal_line, histogram=macd_line - signal_line
    )


def rate_of_change(values: list[float], *, period: int = 12) -> float | None:
    """Compute the most recent Rate of Change, in percent.

    Args:
        values: A price series (typically closes), oldest first.
        period: Number of bars back to compare against.

    Returns:
        `(current - past) / past * 100`, or None if fewer than
        `period + 1` values are given or the reference price is zero.
    """
    if period <= 0 or len(values) < period + 1:
        return None
    past = values[-period - 1]
    if past == 0:
        return None
    return (values[-1] - past) / past * 100.0


def stochastic_oscillator(
    candles: list[Candle], *, k_period: int = 14, d_period: int = 3
) -> tuple[float, float] | None:
    """Compute the most recent %K and %D stochastic oscillator values.

    Args:
        candles: Candles ordered by timestamp ascending.
        k_period: Lookback period for %K's high/low range.
        d_period: Simple moving average period applied to %K to get %D.

    Returns:
        `(percent_k, percent_d)`, or None if there is not enough data.
    """
    if k_period <= 0 or len(candles) < k_period + d_period - 1:
        return None

    percent_k_series: list[float] = []
    for end in range(k_period, len(candles) + 1):
        window = candles[end - k_period : end]
        lowest_low = min(candle.low for candle in window)
        highest_high = max(candle.high for candle in window)
        if highest_high == lowest_low:
            percent_k_series.append(50.0)
            continue
        percent_k_series.append(
            (window[-1].close - lowest_low) / (highest_high - lowest_low) * 100.0
        )

    percent_k = percent_k_series[-1]
    percent_d = sum(percent_k_series[-d_period:]) / d_period
    return percent_k, percent_d


def average_directional_index(candles: list[Candle], *, period: int = 14) -> float | None:
    """Compute the most recent Average Directional Index (ADX, Wilder's method).

    Args:
        candles: Candles ordered by timestamp ascending.
        period: The ADX/DI smoothing period.

    Returns:
        ADX in [0, 100] (trend strength, direction-agnostic), or None if
        there is not enough data.
    """
    if period <= 0 or len(candles) < period * 2 + 1:
        return None

    plus_dm: list[float] = []
    minus_dm: list[float] = []
    true_ranges: list[float] = []
    for i in range(1, len(candles)):
        current, previous = candles[i], candles[i - 1]
        up_move = current.high - previous.high
        down_move = previous.low - current.low
        plus_dm.append(up_move if up_move > down_move and up_move > 0 else 0.0)
        minus_dm.append(down_move if down_move > up_move and down_move > 0 else 0.0)
        true_ranges.append(
            max(
                current.high - current.low,
                abs(current.high - previous.close),
                abs(current.low - previous.close),
            )
        )

    def _wilder_smooth(series: list[float]) -> list[float]:
        smoothed = [sum(series[:period])]
        for value in series[period:]:
            smoothed.append(smoothed[-1] - (smoothed[-1] / period) + value)
        return smoothed

    smoothed_tr = _wilder_smooth(true_ranges)
    smoothed_plus_dm = _wilder_smooth(plus_dm)
    smoothed_minus_dm = _wilder_smooth(minus_dm)

    dx_series: list[float] = []
    for tr, pdm, mdm in zip(smoothed_tr, smoothed_plus_dm, smoothed_minus_dm, strict=True):
        if tr == 0:
            dx_series.append(0.0)
            continue
        plus_di = 100.0 * pdm / tr
        minus_di = 100.0 * mdm / tr
        di_sum = plus_di + minus_di
        dx_series.append(0.0 if di_sum == 0 else 100.0 * abs(plus_di - minus_di) / di_sum)

    return sum(dx_series[-period:]) / period
