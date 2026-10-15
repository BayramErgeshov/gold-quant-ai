"""Indicator math specific to Shakky that does not already exist elsewhere.

EMA/RSI/MACD/ADX are reused as-is from `src.utils.indicators`; ATR is
reused from `src.agents.technical.volatility`; swing highs/lows are
reused from `src.core.technical_analysis.swings`. This module only adds
the pieces the "Classic M5 Strategy" specification requires that were not
already built anywhere in the repo: Bollinger Bands, psychological
(round-number) levels, and a plain support/resistance clustering
function (distinct from `src.agents.technical.support_resistance`'s own
AI-agent-wrapped version -- this one returns bare price levels, never a
`bias`/`confidence` scored `AgentReport`).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from src.core.technical_analysis.swings import find_swing_points
from src.models.candle import Candle

_DEFAULT_BOLLINGER_PERIOD = 20
_DEFAULT_BOLLINGER_STD_DEV = 2.0
_DEFAULT_PSYCH_LEVEL_STEP = 10.0
_DEFAULT_SR_LOOKAROUND = 2
_DEFAULT_SR_CLUSTER_TOLERANCE_PCT = 0.15


@dataclass(frozen=True, slots=True)
class BollingerBands:
    """Bollinger Bands(20, 2) at the most recent candle.

    Attributes:
        middle_band: Simple moving average over the period.
        upper_band: `middle_band + std_dev_multiple * standard deviation`.
        lower_band: `middle_band - std_dev_multiple * standard deviation`.
    """

    middle_band: float
    upper_band: float
    lower_band: float


def bollinger_bands(
    closes: list[float],
    *,
    period: int = _DEFAULT_BOLLINGER_PERIOD,
    std_dev_multiple: float = _DEFAULT_BOLLINGER_STD_DEV,
) -> BollingerBands | None:
    """Compute the most recent Bollinger Bands(20, 2) values.

    Args:
        closes: Close prices, oldest first.
        period: The simple-moving-average / standard-deviation window.
        std_dev_multiple: How many standard deviations the bands sit from
            the middle band.

    Returns:
        The most recent `BollingerBands`, or None if fewer than `period`
        closes are given.
    """
    if period <= 0 or len(closes) < period:
        return None
    window = closes[-period:]
    middle = sum(window) / period
    variance = sum((value - middle) ** 2 for value in window) / period
    std_dev = math.sqrt(variance)
    return BollingerBands(
        middle_band=middle,
        upper_band=middle + std_dev_multiple * std_dev,
        lower_band=middle - std_dev_multiple * std_dev,
    )


def nearest_psychological_levels(
    price: float, *, step: float = _DEFAULT_PSYCH_LEVEL_STEP
) -> tuple[float, float]:
    """Find the nearest round-number ("psychological") levels around a price.

    Args:
        price: The reference price, e.g. the current tick.
        step: The round-number spacing (e.g. 10.0 for XAUUSD's common
            round levels like 2000/2010/2020).

    Returns:
        `(level_below, level_above)`, the nearest multiples of `step`
        below and above `price`. Equal to `price` itself on either side
        if `price` is already an exact multiple of `step`.

    Raises:
        ValueError: If `step` is not positive.
    """
    if step <= 0:
        raise ValueError("step must be positive")
    level_below = math.floor(price / step) * step
    level_above = math.ceil(price / step) * step
    return level_below, level_above


def support_resistance_levels(
    candles: list[Candle],
    *,
    lookaround: int = _DEFAULT_SR_LOOKAROUND,
    cluster_tolerance_pct: float = _DEFAULT_SR_CLUSTER_TOLERANCE_PCT,
) -> tuple[list[float], list[float]]:
    """Cluster recent swing points into plain support/resistance price levels.

    Args:
        candles: Candles ordered by timestamp ascending.
        lookaround: Passed through to `find_swing_points`.
        cluster_tolerance_pct: Swing points within this percent of each
            other's price are merged into one level (averaged).

    Returns:
        `(support_levels, resistance_levels)` -- levels built from swing
        lows and swing highs respectively, each sorted ascending. Empty
        lists if `candles` is too short to find any swing point.
    """
    swings = find_swing_points(candles, lookaround=lookaround)
    lows = sorted(swing.candle.low for swing in swings if swing.kind == "low")
    highs = sorted(swing.candle.high for swing in swings if swing.kind == "high")
    return (
        _cluster_prices(lows, tolerance_pct=cluster_tolerance_pct),
        _cluster_prices(highs, tolerance_pct=cluster_tolerance_pct),
    )


def _cluster_prices(prices: list[float], *, tolerance_pct: float) -> list[float]:
    if not prices:
        return []
    clusters: list[list[float]] = [[prices[0]]]
    for price in prices[1:]:
        cluster_average = sum(clusters[-1]) / len(clusters[-1])
        if cluster_average == 0:
            clusters.append([price])
            continue
        distance_pct = abs(price - cluster_average) / cluster_average * 100
        if distance_pct <= tolerance_pct:
            clusters[-1].append(price)
        else:
            clusters.append([price])
    return [sum(cluster) / len(cluster) for cluster in clusters]


def nearest_support(levels: list[float], price: float) -> float | None:
    """The highest support level at or below `price`, or None if none exists."""
    below = [level for level in levels if level <= price]
    return max(below) if below else None


def nearest_resistance(levels: list[float], price: float) -> float | None:
    """The lowest resistance level at or above `price`, or None if none exists."""
    above = [level for level in levels if level >= price]
    return min(above) if above else None
