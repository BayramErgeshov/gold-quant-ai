"""Swing high/low detection, shared by multiple technical agents.

A standard fractal definition: a candle is a swing high if its high is the
maximum within a symmetric window centered on it (and similarly for swing
lows). Used by Market Structure, Liquidity and Support/Resistance analysis
alike, kept here once rather than duplicated per CODING_STANDARDS.md
("Never duplicate functionality").
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from src.models.candle import Candle

SwingKind = Literal["high", "low"]


@dataclass(frozen=True, slots=True)
class SwingPoint:
    """A single detected swing high or low.

    Attributes:
        index: Position of the swing candle within the input list.
        candle: The swing candle itself.
        kind: "high" or "low".
    """

    index: int
    candle: Candle
    kind: SwingKind


def find_swing_points(candles: list[Candle], *, lookaround: int = 2) -> list[SwingPoint]:
    """Find fractal swing highs/lows in a candle series.

    Args:
        candles: Candles ordered by timestamp ascending.
        lookaround: Number of candles on each side that must be
            lower/higher for a candle to count as a swing point.

    Returns:
        `SwingPoint`s in chronological order. Empty if `candles` is too
        short to evaluate any window.
    """
    swings: list[SwingPoint] = []
    for index in range(lookaround, len(candles) - lookaround):
        window = candles[index - lookaround : index + lookaround + 1]
        candle = candles[index]
        if candle.high == max(item.high for item in window):
            swings.append(SwingPoint(index=index, candle=candle, kind="high"))
        elif candle.low == min(item.low for item in window):
            swings.append(SwingPoint(index=index, candle=candle, kind="low"))
    return swings
