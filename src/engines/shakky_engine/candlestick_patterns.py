"""The five candlestick patterns Shakky is allowed to use: Pin Bar,
Engulfing, Doji, Hammer, Hanging Man.

Reuses `detect_pin_bar`/`detect_engulfing`/`detect_doji`'s own wick/body
ratio math from `src.agents.technical.price_action` -- never the
AI-scored `PriceActionAgent` class around them. Hammer/Hanging Man need
one thing that reusable math doesn't provide: the classical definitions
distinguish an otherwise-identical bullish-shaped pin bar by what
preceded it (a hammer only after a downswing, a hanging man only after
an upswing) -- that trend-context check is new logic added here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from src.agents.technical.price_action import detect_doji, detect_engulfing, detect_pin_bar
from src.models.candle import Candle

_DEFAULT_TREND_LOOKBACK = 5


@dataclass(frozen=True, slots=True)
class CandlestickSignal:
    """One detected candlestick pattern, already resolved to a trade direction.

    Attributes:
        name: "pin_bar" / "bullish_engulfing" / "bearish_engulfing" /
            "doji" / "hammer" / "hanging_man".
        direction: "buy" or "sell". None for a bare doji, which has no
            direction of its own until paired with a separate
            confirmation (per the "Doji + confirmation" entry rule).
    """

    name: str
    direction: Literal["buy", "sell"] | None


def detect_pin_bar_signal(candle: Candle) -> CandlestickSignal | None:
    """Detect a pin bar and resolve its direction from which wick dominates."""
    pattern = detect_pin_bar(candle)
    if pattern is None or pattern.bias == "neutral":
        return None
    return CandlestickSignal(
        name="pin_bar", direction="buy" if pattern.bias == "bullish" else "sell"
    )


def detect_engulfing_signal(previous: Candle, current: Candle) -> CandlestickSignal | None:
    """Detect a bullish/bearish engulfing candle."""
    pattern = detect_engulfing(previous, current)
    if pattern is None or pattern.bias == "neutral":
        return None
    return CandlestickSignal(
        name=pattern.name, direction="buy" if pattern.bias == "bullish" else "sell"
    )


def detect_doji_signal(candle: Candle) -> CandlestickSignal | None:
    """Detect a doji. Always direction=None -- a doji alone never implies a side."""
    pattern = detect_doji(candle)
    if pattern is None:
        return None
    return CandlestickSignal(name="doji", direction=None)


def classify_hammer_or_hanging_man(
    candles: list[Candle], *, trend_lookback: int = _DEFAULT_TREND_LOOKBACK
) -> CandlestickSignal | None:
    """Classify the most recent candle's bullish pin-bar shape as hammer or hanging man.

    Args:
        candles: Candles ordered by timestamp ascending; the last one is checked.
        trend_lookback: How many candles before the pattern candle define
            "the preceding trend" (compared by net close-to-close move).

    Returns:
        `CandlestickSignal(name="hammer", direction="buy")` if the shape
        follows a downswing, `CandlestickSignal(name="hanging_man",
        direction="sell")` if it follows an upswing, or None if there is
        no bullish-shaped pin bar on the most recent candle, not enough
        history to judge the preceding trend, or the preceding trend was
        flat (never a fabricated call from ambiguous context).
    """
    if len(candles) < trend_lookback + 1:
        return None
    pattern = detect_pin_bar(candles[-1])
    if pattern is None or pattern.bias != "bullish":
        return None  # only the long-lower-wick shape is hammer/hanging-man eligible
    preceding = candles[-trend_lookback - 1 : -1]
    preceding_move = preceding[-1].close - preceding[0].close
    if preceding_move < 0:
        return CandlestickSignal(name="hammer", direction="buy")
    if preceding_move > 0:
        return CandlestickSignal(name="hanging_man", direction="sell")
    return None
