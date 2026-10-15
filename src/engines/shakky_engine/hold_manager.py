"""Hold Manager for Shakky (Classic M5 Strategy Engine).

Continuously answers "should the current position still be held?" so
`exit_management` can let a genuinely strong trend run instead of
exiting at a fixed target the moment it's touched. Deliberately fully
deterministic, like the rest of `src.engines.shakky_engine` -- see
`trend_confidence.py`'s own module docstring for why.

Reuses Shakky's own five allowed candlestick patterns
(`candlestick_patterns.py`) to detect a reversal signal forming against
the open position -- the same patterns Shakky's entry logic already
uses, just checked against the *opposite* of the held direction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from src.engines.shakky_engine.candlestick_patterns import (
    classify_hammer_or_hanging_man,
    detect_engulfing_signal,
    detect_pin_bar_signal,
)
from src.engines.shakky_engine.trend_confidence import TrendConfidenceAssessment
from src.models.candle import Candle

Direction = Literal["buy", "sell"]

_MIN_CANDLES_FOR_REVERSAL_CHECK = 2


@dataclass(frozen=True, slots=True)
class HoldAssessment:
    """Whether an open Shakky position should still be held this cycle.

    Attributes:
        should_hold: Whether to continue holding (no exhaustion-driven close this cycle).
        continuation_expected: Whether the move looks likely to keep
            going in the position's favor.
        reversal_expected: Whether a reversal/exhaustion signal against
            the position was detected this cycle.
        reasons: Every contributing signal, human-readable.
    """

    should_hold: bool
    continuation_expected: bool
    reversal_expected: bool
    reasons: list[str] = field(default_factory=list)


def _opposing_candlestick_reasons(
    position_direction: Direction, m5_candles: list[Candle]
) -> list[str]:
    if len(m5_candles) < _MIN_CANDLES_FOR_REVERSAL_CHECK:
        return []
    opposite: Direction = "sell" if position_direction == "buy" else "buy"
    reasons: list[str] = []

    pin_bar = detect_pin_bar_signal(m5_candles[-1])
    if pin_bar is not None and pin_bar.direction == opposite:
        reasons.append("opposing_pin_bar")

    engulfing = detect_engulfing_signal(m5_candles[-2], m5_candles[-1])
    if engulfing is not None and engulfing.direction == opposite:
        reasons.append(f"opposing_{engulfing.name}")

    hammer_or_hanging = classify_hammer_or_hanging_man(m5_candles)
    if hammer_or_hanging is not None and hammer_or_hanging.direction == opposite:
        reasons.append(f"opposing_{hammer_or_hanging.name}")

    return reasons


def assess_hold(
    *,
    position_direction: Direction,
    trend_confidence: TrendConfidenceAssessment,
    m5_candles: list[Candle],
) -> HoldAssessment:
    """Decide whether an open Shakky position should still be held this cycle.

    Args:
        position_direction: The open position's own direction.
        trend_confidence: This cycle's fresh `assess_trend_confidence()`
            result, computed for `position_direction`.
        m5_candles: Primary M5 candles, ordered by timestamp ascending.

    Returns:
        A `HoldAssessment`. Either an opposing candlestick pattern or
        Trend Confidence dropping back to "minor" (the move has visibly
        lost the strength it had) counts as exhaustion evidence -- never
        a close on the mere fact that price paused.
    """
    opposing_reasons = _opposing_candlestick_reasons(position_direction, m5_candles)
    trend_exhausted = trend_confidence.level == "minor"
    reversal_expected = bool(opposing_reasons) or trend_exhausted
    continuation_expected = trend_confidence.continuation_likely and not reversal_expected

    reasons = [*trend_confidence.reasons, *opposing_reasons]
    if trend_exhausted:
        reasons.append("trend_confidence_dropped_to_minor")
    if continuation_expected:
        reasons.append("continuation_signals_intact")

    return HoldAssessment(
        should_hold=not reversal_expected,
        continuation_expected=continuation_expected,
        reversal_expected=reversal_expected,
        reasons=reasons,
    )
