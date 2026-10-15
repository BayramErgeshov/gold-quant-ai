"""Micro Scalping-specific post-trade learning (Self Learning Engine extension).

Per the engine's own spec ("post-trade learning: entry/exit quality,
too-early/too-late profit-taking, would holding longer have helped"),
extended with the questions specific to Micro Scalping's own move
management (dynamic profit target + trailing stop, hard max-holding-time
cap) that the generic `src.engines.learning_engine.post_mortem` report --
built around Chief AI's department-vote shape, which Micro Scalping's own
`Trade.department_votes` never populates -- cannot meaningfully answer.

Mirrors `src.engines.learning_engine.shakky_trade_review`'s own shape and
honesty guarantee: every verdict here is a heuristic *hypothesis* derived
only from already-persisted `Trade` fields, never a claimed fact about
what would definitely have happened (CLAUDE.md: "Always distinguish
between... Hypotheses... Unknowns"). Unlike Shakky, Micro Scalping never
sets a broker-side `take_profit`, so "too small/large a target" has no
meaning here -- the equivalent questions are framed against the realized
exit itself and the position's own initial risk distance instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.models.trade import Trade

# How far MFE must exceed the realized favorable move at exit to count as
# "the move kept going after we closed," rather than ordinary price noise
# right around the exit itself.
_MEANINGFUL_MFE_EXCESS_FRACTION = 0.3
# How much of the original risk distance (entry to initial stop) MFE must
# reach for a trade that closed flat/negative to count as "it did move
# favorably first, then reversed before we got out" rather than "it just
# never worked."
_MEANINGFUL_MFE_FOR_REVERSAL_FRACTION = 0.5
# How close to the configured max holding time (as a fraction of it) a
# trade's actual holding duration must reach to count as "closed by the
# hard time cap rather than by its own profit/momentum logic."
_MAX_HOLDING_TIME_PROXIMITY_FRACTION = 0.95
_DEFAULT_MAX_HOLDING_MINUTES = 30.0


@dataclass(frozen=True, slots=True)
class MicroScalpingLearningVerdict:
    """One closed Micro Scalping trade's own learning verdict (heuristic, not fact).

    Attributes:
        closed_too_early: Price kept moving favorably well past the
            realized exit (`Trade.max_favorable_excursion` meaningfully
            exceeds the realized favorable move) -- the trailing stop
            may have been too tight, or momentum was still strong when
            this engine chose to close flat.
        gave_back_profit: The position reached a meaningful favorable
            excursion first, then closed at breakeven or a loss -- the
            trailing distance (or the decision not to trail) let a
            genuine reversal erase an already-earned gain.
        held_too_long: The trade's holding duration reached the
            configured max-holding-time cap -- it needed the hard safety
            exit rather than closing via its own profit-target/momentum
            logic, the opposite of the engine's own "seconds to several
            minutes" design goal.
        reasons: Every contributing observation, human-readable.
    """

    closed_too_early: bool = False
    gave_back_profit: bool = False
    held_too_long: bool = False
    reasons: list[str] = field(default_factory=list)


def review_micro_scalping_trade(
    trade: Trade, *, max_holding_minutes: float = _DEFAULT_MAX_HOLDING_MINUTES
) -> MicroScalpingLearningVerdict:
    """Build a Micro Scalping-specific post-trade learning verdict.

    Args:
        trade: A closed Micro Scalping `Trade` (magic-number-filtered by the caller).
        max_holding_minutes: The `RuntimeSettings.micro_scalping_max_holding_minutes`
            value in effect for this trade, if known, else the engine's
            own constructed default.

    Returns:
        A `MicroScalpingLearningVerdict`.
    """
    if trade.entry_price is None or trade.exit_price is None or trade.initial_stop_loss is None:
        return MicroScalpingLearningVerdict(reasons=["insufficient_trade_data"])

    reasons: list[str] = []
    risk_distance = abs(trade.entry_price - trade.initial_stop_loss)
    mfe = trade.max_favorable_excursion or 0.0
    realized_favorable_move = (
        trade.exit_price - trade.entry_price
        if trade.direction == "buy"
        else trade.entry_price - trade.exit_price
    )

    closed_too_early = (
        mfe > 0
        and realized_favorable_move > 0
        and mfe > (realized_favorable_move * (1 + _MEANINGFUL_MFE_EXCESS_FRACTION))
    )
    if closed_too_early:
        reasons.append(
            f"mfe={mfe:.2f}_exceeds_realized_favorable_move={realized_favorable_move:.2f}_by_over_"
            f"{_MEANINGFUL_MFE_EXCESS_FRACTION:.0%}"
        )

    gave_back_profit = (
        risk_distance > 0
        and mfe >= risk_distance * _MEANINGFUL_MFE_FOR_REVERSAL_FRACTION
        and (trade.realized_pnl or 0.0) <= 0
    )
    if gave_back_profit:
        reasons.append(
            f"mfe={mfe:.2f}_reached_{_MEANINGFUL_MFE_FOR_REVERSAL_FRACTION:.0%}_of_risk_"
            "but_trade_closed_flat_or_negative"
        )

    held_too_long = False
    if trade.opened_at is not None and trade.closed_at is not None and max_holding_minutes > 0:
        holding_minutes = (trade.closed_at - trade.opened_at).total_seconds() / 60.0
        held_too_long = (
            holding_minutes >= max_holding_minutes * _MAX_HOLDING_TIME_PROXIMITY_FRACTION
        )
        if held_too_long:
            reasons.append(
                f"holding_minutes={holding_minutes:.1f}_reached_max_holding_cap={max_holding_minutes:.1f}"
            )

    return MicroScalpingLearningVerdict(
        closed_too_early=closed_too_early,
        gave_back_profit=gave_back_profit,
        held_too_long=held_too_long,
        reasons=reasons,
    )


__all__ = ["MicroScalpingLearningVerdict", "review_micro_scalping_trade"]
