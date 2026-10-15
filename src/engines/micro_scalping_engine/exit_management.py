"""Dynamic profit management for Micro Scalping.

Per the engine's own spec: capture small moves fast, but "if momentum
remains exceptionally strong, allow the trade to continue using a
trailing stop instead of closing immediately." Deliberately fully
deterministic, mirroring `src.engines.shakky_engine.exit_management`'s
own shape -- the trailing stop only ever moves further in the
position's favor (never retreats), same invariant as
`src.engines.risk_engine.dynamic_stop`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Direction = Literal["buy", "sell"]
ExitAction = Literal["hold", "trail", "close_full"]

# How far (in ATR multiples) the trailing stop sits behind the current
# price once the profit target has been reached and momentum still
# supports holding -- tight enough to still lock in most of the small
# target already earned if price reverses.
_TRAIL_ATR_MULTIPLE = 0.5


@dataclass(frozen=True, slots=True)
class MicroScalpingExitDecision:
    """What to do with an open Micro Scalping position this cycle, and why.

    Attributes:
        action: "hold" (target not yet reached, or trailing stop already
            optimal), "trail" (move the stop to lock in profit while
            letting a strong move continue), or "close_full" (secure
            profit now, or a hard safety exit).
        new_stop_loss: The new stop price, only set for "trail".
        reasons: Every contributing signal, human-readable.
    """

    action: ExitAction
    new_stop_loss: float | None
    reasons: list[str] = field(default_factory=list)


def _trailing_stop_price(direction: Direction, current_price: float, atr: float) -> float:
    distance = atr * _TRAIL_ATR_MULTIPLE
    return current_price - distance if direction == "buy" else current_price + distance


def evaluate_exit(
    *,
    direction: Direction,
    floating_profit_usd: float,
    min_profit_target_usd: float,
    momentum_still_strong: bool,
    current_price: float,
    current_stop_loss: float,
    atr: float,
    holding_minutes: float,
    max_holding_minutes: float,
    trailing_stop_enabled: bool,
) -> MicroScalpingExitDecision:
    """Decide what to do with an open Micro Scalping position this cycle.

    Args:
        direction: The position's own direction.
        floating_profit_usd: Current floating profit/loss in account
            currency (`OpenPosition.profit` -- the broker's own figure,
            never recomputed from price/volume here).
        min_profit_target_usd: The configured minimum profit to close
            (or consider trailing) at.
        momentum_still_strong: Whether a fresh momentum burst in this
            position's own favor was detected this cycle (`entry_filters
            .check_momentum`), combined with Trend Confidence still
            reading strong/exceptional -- the caller's own combined
            "is this move still genuinely accelerating" verdict.
        current_price: The position's current market price.
        current_stop_loss: The position's current stop-loss price.
        atr: Current M1/M5 Average True Range, for the trailing distance.
        holding_minutes: How long the position has been open.
        max_holding_minutes: Hard cap -- closed unconditionally once
            reached, per "never hold trades for hours."
        trailing_stop_enabled: When False, this engine never trails --
            it only ever closes flat at the profit target.

    Returns:
        A `MicroScalpingExitDecision`.
    """
    if holding_minutes >= max_holding_minutes:
        return MicroScalpingExitDecision(
            action="close_full",
            new_stop_loss=None,
            reasons=[
                f"max_holding_time_reached:{holding_minutes:.1f}>={max_holding_minutes:.1f}min"
            ],
        )

    if floating_profit_usd < min_profit_target_usd:
        return MicroScalpingExitDecision(
            action="hold",
            new_stop_loss=None,
            reasons=[
                f"profit_below_target:{floating_profit_usd:.2f}<{min_profit_target_usd:.2f}usd"
            ],
        )

    if trailing_stop_enabled and momentum_still_strong:
        candidate_stop = _trailing_stop_price(direction, current_price, atr)
        is_improvement = (
            candidate_stop > current_stop_loss
            if direction == "buy"
            else candidate_stop < current_stop_loss
        )
        if is_improvement:
            return MicroScalpingExitDecision(
                action="trail",
                new_stop_loss=candidate_stop,
                reasons=["momentum_still_strong_trailing_stop"],
            )
        return MicroScalpingExitDecision(
            action="hold",
            new_stop_loss=None,
            reasons=["momentum_still_strong_stop_already_optimal"],
        )

    return MicroScalpingExitDecision(
        action="close_full",
        new_stop_loss=None,
        reasons=(
            ["profit_target_reached_momentum_weakening"]
            if trailing_stop_enabled
            else ["profit_target_reached_trailing_disabled"]
        ),
    )
