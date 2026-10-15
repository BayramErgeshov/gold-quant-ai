"""Shakky (Classic M5 Strategy Engine) orchestrator.

Per its own production requirement: a completely independent, purely
rule-based engine that must NOT use Chief AI decision logic, the Trade
Quality Engine, Books Intelligence, Machine Learning, Historical Pattern
Matching, the News Engine, the Correlation Engine (except DXY), Smart
Money, Order Flow, or any existing AI scoring. Every decision here comes
from `src.engines.shakky_engine.confirmations`'s plain, deterministic
confirmation counting -- never a blended confidence score.

Primary decision timeframe is M5; M15/H1/H4/D1 are independent
confirmation timeframes checked with the same EMA9/21/50 trend-stack
logic as the M5 Trend Following confirmation itself, deliberately not
reusing `src.engines.chief_ai.multi_timeframe` (that module lives in the
`chief_ai` package this engine must stay independent of) -- a small,
self-contained duplication of the *concept*, not the code, is the
correct tradeoff here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from src.agents.technical.volatility import average_true_range
from src.core.execution.mt5_client import SymbolTick
from src.engines.shakky_engine.confirmations import (
    Confirmation,
    collect_confirmations,
    resolve_entry_signal,
)
from src.engines.shakky_engine.indicators import (
    nearest_resistance,
    nearest_support,
    support_resistance_levels,
)
from src.models.candle import Candle
from src.utils.indicators import exponential_moving_average

Direction = Literal["buy", "sell"]

_EMA_FAST_PERIOD = 9
_EMA_MID_PERIOD = 21
_EMA_SLOW_PERIOD = 50
_ATR_PERIOD = 14
_MIN_M5_CANDLES = 60
_MIN_TIMEFRAME_CANDLES_FOR_TREND = 60
_TREND_FOLLOWING_STOP_ATR_MULTIPLE = 1.5
_MOMENTUM_STOP_ATR_MULTIPLE = 1.5
_MEAN_REVERSION_STOP_ATR_MULTIPLE = 1.0
_INTERMARKET_STOP_ATR_MULTIPLE = 1.2
_CANDLESTICK_STOP_ATR_BUFFER = 0.2
_TAKE_PROFIT_FALLBACK_RR_MULTIPLE = 2.0
# See `_is_stop_loss_valid` for why this floor exists and why it is
# deliberately far smaller than any family's real stop distance (all >= 0.2x ATR).
_MIN_STOP_DISTANCE_ATR_FRACTION = 0.05
# A dominant family is picked (by count of agreeing confirmations, ties
# broken by this fixed priority order) to decide the stop-loss basis --
# "Stop Loss: According to the active strategy."
_FAMILY_PRIORITY: tuple[str, ...] = (
    "candlestick",
    "mean_reversion",
    "intermarket",
    "momentum",
    "trend_following",
)


@dataclass(frozen=True, slots=True)
class ShakkySignal:
    """A single actionable Classic M5 Strategy opportunity.

    Attributes:
        direction: "buy" or "sell".
        entry_price: Planned entry price (current tick).
        stop_loss: Protective stop, sized per the dominant confirming
            family's own rule (candlestick pattern extreme, ATR
            multiple, etc).
        take_profit: Target price at the nearest opposing support/
            resistance level ("market structure"), or an ATR-based
            fallback if no level was found.
        confirmations: Every confirmation that agreed with `direction`.
        dominant_family: Which entry-logic family's stop-loss rule was used.
        reasons: Human-readable detail from every agreeing confirmation.
    """

    direction: Direction
    entry_price: float
    stop_loss: float
    take_profit: float
    confirmations: list[Confirmation]
    dominant_family: str
    reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ShakkyAnalysisOutcome:
    """Shakky's outcome for one cycle -- always returned, win or no-trade.

    Attributes:
        signal: The actionable signal, if at least three confirmations
            agreed on one direction and the confirmation timeframes did
            not net-disagree. None means no trade this cycle.
        direction: The best directional read this cycle, if any
            confirmation was found at all (even below the 3-confirmation
            minimum). None when no confirmation fired in either direction.
        confirmation_count: How many confirmations agreed with `direction`.
        reasons: Every confirmation detail, or the specific reason this
            cycle did not qualify -- never a silently discarded "why not."
    """

    signal: ShakkySignal | None
    direction: Direction | None = None
    confirmation_count: int = 0
    reasons: list[str] = field(default_factory=list)


def _trend_stack_direction(candles: list[Candle]) -> Direction | None:
    """The EMA9/21/50 stack direction for one timeframe, or None if not stacked/insufficient."""
    if len(candles) < _MIN_TIMEFRAME_CANDLES_FOR_TREND:
        return None
    closes = [candle.close for candle in candles]
    fast = exponential_moving_average(closes, period=_EMA_FAST_PERIOD)
    mid = exponential_moving_average(closes, period=_EMA_MID_PERIOD)
    slow = exponential_moving_average(closes, period=_EMA_SLOW_PERIOD)
    if fast is None or mid is None or slow is None:
        return None
    ema9, ema21, ema50 = fast[-1], mid[-1], slow[-1]
    if ema9 > ema21 > ema50:
        return "buy"
    if ema9 < ema21 < ema50:
        return "sell"
    return None


def _multi_timeframe_reasons(
    timeframe_candles: dict[str, list[Candle] | None], direction: Direction
) -> tuple[int, int, list[str]]:
    """Check each confirmation timeframe's own EMA trend stack against `direction`.

    Returns:
        `(agree_count, disagree_count, reasons)` -- a timeframe with too
        little history or no clear stack contributes to neither count
        (an honest "no opinion," never a fabricated agreement).
    """
    agree = 0
    disagree = 0
    reasons: list[str] = []
    for name, candles in timeframe_candles.items():
        if candles is None:
            continue
        stack_direction = _trend_stack_direction(candles)
        if stack_direction is None:
            continue
        if stack_direction == direction:
            agree += 1
            reasons.append(f"{name}_confirms")
        else:
            disagree += 1
            reasons.append(f"{name}_disagrees")
    return agree, disagree, reasons


def _dominant_family(confirmations: list[Confirmation]) -> str:
    counts: dict[str, int] = {}
    for confirmation in confirmations:
        counts[confirmation.family] = counts.get(confirmation.family, 0) + 1
    best_count = max(counts.values())
    for family in _FAMILY_PRIORITY:
        if counts.get(family) == best_count:
            return family
    return confirmations[
        0
    ].family  # pragma: no cover - unreachable: every family is in the priority list


def _is_stop_loss_valid(
    *, direction: Direction, entry_price: float, stop_loss: float, atr: float
) -> bool:
    """Reject a stop that has ended up on the wrong side of (or too close to) entry.

    The candlestick family's stop is anchored to the pattern candle's own
    high/low, not to `entry_price` -- if price drifts past that fixed
    level before the order actually reaches the broker, the stop can end
    up on the wrong side of entry entirely (e.g. a sell whose stop is now
    below the current price), which MT5 correctly rejects as "Invalid
    stops" (retcode 10016). This floor is deliberately far smaller than
    any family's real stop distance (all >= 0.2x ATR), so it only ever
    triggers on this degenerate case, never on a legitimately computed stop.
    """
    stop_distance_from_entry = (
        entry_price - stop_loss if direction == "buy" else stop_loss - entry_price
    )
    return stop_distance_from_entry >= atr * _MIN_STOP_DISTANCE_ATR_FRACTION


def _stop_loss(
    *,
    family: str,
    m5_candles: list[Candle],
    direction: Direction,
    entry_price: float,
    atr: float,
) -> float:
    """Protective stop, sized per the dominant confirming family's own rule."""
    if family == "candlestick":
        pattern_candle = m5_candles[-1]
        buffer = atr * _CANDLESTICK_STOP_ATR_BUFFER
        return pattern_candle.low - buffer if direction == "buy" else pattern_candle.high + buffer
    multiple = {
        "mean_reversion": _MEAN_REVERSION_STOP_ATR_MULTIPLE,
        "intermarket": _INTERMARKET_STOP_ATR_MULTIPLE,
        "momentum": _MOMENTUM_STOP_ATR_MULTIPLE,
        "trend_following": _TREND_FOLLOWING_STOP_ATR_MULTIPLE,
    }[family]
    distance = atr * multiple
    return entry_price - distance if direction == "buy" else entry_price + distance


def _take_profit(
    *,
    direction: Direction,
    entry_price: float,
    stop_loss: float,
    support_levels: list[float],
    resistance_levels: list[float],
) -> float:
    """Target at the nearest opposing market-structure level, or an ATR/RR fallback."""
    stop_distance = abs(entry_price - stop_loss)
    if direction == "buy":
        level = nearest_resistance(resistance_levels, entry_price)
        if level is not None and level > entry_price:
            return level
        return entry_price + stop_distance * _TAKE_PROFIT_FALLBACK_RR_MULTIPLE
    level = nearest_support(support_levels, entry_price)
    if level is not None and level < entry_price:
        return level
    return entry_price - stop_distance * _TAKE_PROFIT_FALLBACK_RR_MULTIPLE


class ShakkyAnalysisService:
    """Runs the Classic M5 Strategy Engine's full analysis cycle."""

    def __init__(self, *, atr_period: int = _ATR_PERIOD) -> None:
        """Initialize the service (constructor injection).

        Args:
            atr_period: M5 bars to average True Range over, for stop/target sizing.
        """
        self._atr_period = atr_period

    async def analyze(
        self,
        *,
        m5_candles: list[Candle],
        m15_candles: list[Candle] | None,
        h1_candles: list[Candle] | None,
        h4_candles: list[Candle] | None,
        d1_candles: list[Candle] | None,
        dxy_candles: list[Candle] | None,
        tick: SymbolTick,
    ) -> ShakkyAnalysisOutcome:
        """Run one full Classic M5 Strategy analysis cycle.

        Args:
            m5_candles: Primary M5 candles, ordered by timestamp ascending.
            m15_candles: M15 confirmation candles, if available.
            h1_candles: H1 confirmation candles, if available.
            h4_candles: H4 confirmation candles, if available.
            d1_candles: D1 confirmation candles, if available.
            dxy_candles: Recent DXY candles for the Intermarket family, if configured.
            tick: The current bid/ask quote -- entry price is resolved to
                `tick.ask`/`tick.bid` only once a direction is known
                (never before, which would bias the confirmation math
                toward whichever side happened to be quoted).

        Returns:
            A `ShakkyAnalysisOutcome`, always -- `.signal` is None when
            fewer than three confirmations agree, the confirmation
            timeframes net-disagree, or ATR is undefined -- never a
            fabricated trade.
        """
        if len(m5_candles) < _MIN_M5_CANDLES:
            return ShakkyAnalysisOutcome(signal=None, reasons=["insufficient_m5_history"])

        confirmations = collect_confirmations(m5_candles=m5_candles, dxy_candles=dxy_candles)
        resolved = resolve_entry_signal(confirmations)
        if resolved is None:
            buy_count = sum(1 for c in confirmations if c.direction == "buy")
            sell_count = sum(1 for c in confirmations if c.direction == "sell")
            direction: Direction | None = None
            if buy_count > sell_count:
                direction = "buy"
            elif sell_count > buy_count:
                direction = "sell"
            return ShakkyAnalysisOutcome(
                signal=None,
                direction=direction,
                confirmation_count=max(buy_count, sell_count),
                reasons=[
                    f"insufficient_confirmations:{max(buy_count, sell_count)}<3",
                    *(c.detail for c in confirmations),
                ],
            )
        direction, agreeing = resolved
        entry_price = tick.ask if direction == "buy" else tick.bid
        reasons = [c.detail for c in agreeing]

        agree, disagree, mtf_reasons = _multi_timeframe_reasons(
            {"m15": m15_candles, "h1": h1_candles, "h4": h4_candles, "d1": d1_candles}, direction
        )
        reasons.extend(mtf_reasons)
        if disagree > agree:
            reasons.append("multi_timeframe_net_disagreement")
            return ShakkyAnalysisOutcome(
                signal=None,
                direction=direction,
                confirmation_count=len(agreeing),
                reasons=reasons,
            )

        atr = average_true_range(m5_candles, period=self._atr_period)
        if atr is None or atr <= 0:
            reasons.append("undefined_atr")
            return ShakkyAnalysisOutcome(
                signal=None,
                direction=direction,
                confirmation_count=len(agreeing),
                reasons=reasons,
            )

        family = _dominant_family(agreeing)
        stop_loss = _stop_loss(
            family=family,
            m5_candles=m5_candles,
            direction=direction,
            entry_price=entry_price,
            atr=atr,
        )
        if not _is_stop_loss_valid(
            direction=direction, entry_price=entry_price, stop_loss=stop_loss, atr=atr
        ):
            reasons.append("stop_loss_invalid_relative_to_entry")
            return ShakkyAnalysisOutcome(
                signal=None,
                direction=direction,
                confirmation_count=len(agreeing),
                reasons=reasons,
            )
        support_levels, resistance_levels = support_resistance_levels(m5_candles)
        take_profit = _take_profit(
            direction=direction,
            entry_price=entry_price,
            stop_loss=stop_loss,
            support_levels=support_levels,
            resistance_levels=resistance_levels,
        )

        signal = ShakkySignal(
            direction=direction,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            confirmations=agreeing,
            dominant_family=family,
            reasons=reasons,
        )
        return ShakkyAnalysisOutcome(
            signal=signal, direction=direction, confirmation_count=len(agreeing), reasons=reasons
        )
