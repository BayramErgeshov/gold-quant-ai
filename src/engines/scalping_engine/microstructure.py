"""M1/M5 microstructure analysis for the Scalping Engine.

Per this platform's operating instructions: the Scalping Engine "must
operate mainly on M1 and M5" and continuously analyze "Momentum bursts,
Breakout failures, Micro pullbacks... Spread changes... Session timing."
Every function here is a small, explainable, independently testable rule
over a short window of recent candles/ticks — never a black-box signal.

Reuses `src.agents.technical.volatility.average_true_range` for ATR
rather than recomputing it (CODING_STANDARDS.md "Never duplicate
functionality").
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from src.agents.technical.volatility import average_true_range
from src.models.candle import Candle

_DEFAULT_ATR_PERIOD = 14
_MOMENTUM_BURST_ATR_MULTIPLE = 1.5
_MOMENTUM_BURST_LOOKBACK = 3
_MICRO_PULLBACK_MAX_RETRACE_PCT = 0.4
_MICRO_PULLBACK_MIN_IMPULSE_ATR_MULTIPLE = 1.0

Session = Literal["asia", "london", "new_york", "london_new_york_overlap", "closed"]


@dataclass(frozen=True, slots=True)
class MomentumBurst:
    """A short run of candles whose combined move is unusually large vs ATR.

    Attributes:
        direction: "bullish" or "bearish".
        move_pct: The burst's net price move, as a percent of its start price.
        atr_multiple: The burst's absolute move divided by the ATR baseline
            — how many "average bars" it moved in `_MOMENTUM_BURST_LOOKBACK` bars.
    """

    direction: Literal["bullish", "bearish"]
    move_pct: float
    atr_multiple: float


def detect_momentum_burst(
    candles: list[Candle], *, atr_period: int = _DEFAULT_ATR_PERIOD
) -> MomentumBurst | None:
    """Detect a recent short, unusually large directional move.

    Args:
        candles: Candles ordered by timestamp ascending.
        atr_period: Bars to average True Range over for the baseline.

    Returns:
        A `MomentumBurst` if the last `_MOMENTUM_BURST_LOOKBACK` candles
        moved at least `_MOMENTUM_BURST_ATR_MULTIPLE` times the ATR
        baseline, else None — never a fabricated burst from insufficient
        or unremarkable data.
    """
    atr = average_true_range(candles, period=atr_period)
    if atr is None or atr <= 0 or len(candles) < _MOMENTUM_BURST_LOOKBACK + 1:
        return None

    window = candles[-_MOMENTUM_BURST_LOOKBACK:]
    start_price = window[0].open
    end_price = window[-1].close
    if start_price <= 0:
        return None

    move = end_price - start_price
    atr_multiple = abs(move) / atr
    if atr_multiple < _MOMENTUM_BURST_ATR_MULTIPLE:
        return None

    return MomentumBurst(
        direction="bullish" if move > 0 else "bearish",
        move_pct=move / start_price * 100,
        atr_multiple=atr_multiple,
    )


@dataclass(frozen=True, slots=True)
class BreakoutFailure:
    """The most recent candle broke a short-term high/low and closed back inside.

    Attributes:
        direction: "bullish" (failed breakdown -> reversal up) or "bearish"
            (failed breakout -> reversal down).
        broken_level: The recent high/low price that was breached and rejected.
    """

    direction: Literal["bullish", "bearish"]
    broken_level: float


def detect_breakout_failure(candles: list[Candle], *, lookback: int = 10) -> BreakoutFailure | None:
    """Detect the latest candle wicking beyond a recent range and closing back inside.

    Args:
        candles: Candles ordered by timestamp ascending.
        lookback: Number of prior candles (excluding the latest) defining
            the recent high/low range.

    Returns:
        A `BreakoutFailure`, or None if there is too little history or no
        failed breakout on the latest candle.
    """
    if len(candles) < lookback + 1:
        return None

    prior = candles[-lookback - 1 : -1]
    latest = candles[-1]
    recent_high = max(candle.high for candle in prior)
    recent_low = min(candle.low for candle in prior)

    if latest.high > recent_high and latest.close < recent_high:
        return BreakoutFailure(direction="bearish", broken_level=recent_high)
    if latest.low < recent_low and latest.close > recent_low:
        return BreakoutFailure(direction="bullish", broken_level=recent_low)
    return None


@dataclass(frozen=True, slots=True)
class MicroPullback:
    """A brief, shallow retracement against a recent strong impulse move.

    Attributes:
        direction: The impulse's (and expected continuation's) direction.
        retrace_pct: How much of the impulse move the pullback retraced,
            in [0.0, 1.0].
    """

    direction: Literal["bullish", "bearish"]
    retrace_pct: float


def detect_micro_pullback(
    candles: list[Candle], *, atr_period: int = _DEFAULT_ATR_PERIOD
) -> MicroPullback | None:
    """Detect a shallow pullback against a recent strong impulse move.

    Args:
        candles: Candles ordered by timestamp ascending. Uses the
            second-to-last candle's move as the "impulse" and the last
            candle as the candidate "pullback".
        atr_period: Bars to average True Range over for the impulse-size baseline.

    Returns:
        A `MicroPullback` if the impulse was large (>= ATR baseline) and
        the pullback retraced no more than
        `_MICRO_PULLBACK_MAX_RETRACE_PCT` of it, else None.
    """
    atr = average_true_range(candles, period=atr_period)
    if atr is None or atr <= 0 or len(candles) < 2:
        return None

    impulse, pullback = candles[-2], candles[-1]
    impulse_move = impulse.close - impulse.open
    if abs(impulse_move) < atr * _MICRO_PULLBACK_MIN_IMPULSE_ATR_MULTIPLE:
        return None

    direction: Literal["bullish", "bearish"] = "bullish" if impulse_move > 0 else "bearish"
    pullback_move = pullback.close - impulse.close
    # A genuine pullback moves opposite to the impulse.
    is_opposing = (direction == "bullish" and pullback_move < 0) or (
        direction == "bearish" and pullback_move > 0
    )
    if not is_opposing:
        return None

    retrace_pct = abs(pullback_move) / abs(impulse_move)
    if retrace_pct > _MICRO_PULLBACK_MAX_RETRACE_PCT:
        return None

    return MicroPullback(direction=direction, retrace_pct=retrace_pct)


def classify_session(timestamp: datetime) -> Session:
    """Classify a UTC timestamp into a standard FX trading session.

    Uses the conventional UTC session hours (London 07-16, New York
    12-21, Tokyo/Asia 23-08); the London/New York overlap (12-16 UTC) is
    reported distinctly since it is the platform's highest-liquidity window.

    Args:
        timestamp: A timezone-aware (or assumed-UTC) datetime.

    Returns:
        One of `Session`.
    """
    hour = (timestamp.astimezone(UTC) if timestamp.tzinfo else timestamp).hour
    in_london = 7 <= hour < 16
    in_new_york = 12 <= hour < 21
    in_asia = hour >= 23 or hour < 8

    if in_london and in_new_york:
        return "london_new_york_overlap"
    if in_london:
        return "london"
    if in_new_york:
        return "new_york"
    if in_asia:
        return "asia"
    return "closed"


def compute_spread_change_pct(recent_spreads: list[float]) -> float:
    """Measure how much the most recent spread deviates from its recent average.

    Args:
        recent_spreads: Recent spread readings (ask - bid), oldest first.
            The last element is treated as "now".

    Returns:
        `(latest - average_of_rest) / average_of_rest * 100`. `0.0` if
        there are fewer than 2 readings or the baseline average is zero
        — never a fabricated spike from insufficient data.
    """
    if len(recent_spreads) < 2:
        return 0.0
    baseline = recent_spreads[:-1]
    average_baseline = sum(baseline) / len(baseline)
    if average_baseline <= 0:
        return 0.0
    return (recent_spreads[-1] - average_baseline) / average_baseline * 100
