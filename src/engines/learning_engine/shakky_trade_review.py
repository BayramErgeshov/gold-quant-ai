"""Shakky-specific post-trade learning (Self Learning Engine extension).

Per the "Post Trade Learning" production requirement, extended with the
questions specific to Shakky's own move-management logic (Trend
Confidence, Dynamic TP, Hold Manager, Position Scaling) that the generic
`src.engines.learning_engine.post_mortem` report -- built around Chief
AI's department-vote shape, which Shakky's own `Trade.department_votes`
never populates -- cannot meaningfully answer.

Every verdict here is a heuristic *hypothesis* derived only from
already-persisted `Trade` fields, never a claimed fact about what
would definitely have happened (CLAUDE.md: "Always distinguish
between... Hypotheses... Unknowns"). Feeds into the existing
`ImprovementProposal` pipeline (`src.engines.learning_engine.hypothesis`/
`proposal`) for recurring patterns -- always a pending proposal
requiring explicit user approval, never an automatic change.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.engines.statistics_engine.trade_performance_report import (
    build_performance_report,
    classify_strategy,
)
from src.models.trade import Trade

# How far MFE must exceed the entry-to-target distance to count as a
# meaningful "the move kept going past the fixed target" signal, rather
# than ordinary price noise around the target itself.
_MEANINGFUL_MFE_EXCESS_FRACTION = 0.3
# How close the exit price must be to the take-profit (as a fraction of
# the original risk distance) to treat the trade as "closed at target."
_TP_HIT_TOLERANCE_FRACTION = 0.1
# How much of the original risk distance MFE must reach for a reversed
# trade to count as "it did move favorably first" rather than "it just
# never worked."
_MEANINGFUL_MFE_FOR_REVERSAL_FRACTION = 0.5
_STRONG_R_MULTIPLE_FOR_SHOULD_HAVE_SCALED = 1.5


@dataclass(frozen=True, slots=True)
class ShakkyLearningVerdict:
    """One closed Shakky trade's Shakky-specific learning verdict (heuristic, not fact).

    Attributes:
        tp_too_small: Price moved meaningfully past the entry-to-target
            distance while the position was open
            (`Trade.max_favorable_excursion` exceeds it) -- a fixed
            target may have capped a bigger move.
        tp_too_large: The position closed at a loss/breakeven without
            reaching its target, despite a meaningful favorable
            excursion first -- the target may have been set beyond what
            the move could realistically reach.
        should_have_scaled: The trade closed with a strong realized
            R-multiple, had an entry-time Trend Confidence score, and
            never scaled in -- a plausible missed Position Scaling
            opportunity, not proof one would actually have triggered
            (this platform does not retain a full history of the Trend
            Confidence score at every intermediate cycle).
        better_strategy: The name of another strategy whose own overall
            average R-multiple is notably higher than this trade's own
            realized R-multiple. None if no comparison data was
            supplied or no other strategy outperformed.
        reasons: Every contributing observation, human-readable.
    """

    tp_too_small: bool = False
    tp_too_large: bool = False
    should_have_scaled: bool = False
    better_strategy: str | None = None
    reasons: list[str] = field(default_factory=list)


def _r_multiple(trade: Trade) -> float | None:
    if trade.entry_price is None or trade.exit_price is None or trade.initial_stop_loss is None:
        return None
    risk_distance = abs(trade.entry_price - trade.initial_stop_loss)
    if risk_distance <= 0:
        return None
    signed_move = (
        trade.exit_price - trade.entry_price
        if trade.direction == "buy"
        else trade.entry_price - trade.exit_price
    )
    return signed_move / risk_distance


def review_shakky_trade(
    trade: Trade, *, other_strategy_average_r_multiple: dict[str, float] | None = None
) -> ShakkyLearningVerdict:
    """Build a Shakky-specific post-trade learning verdict.

    Args:
        trade: A closed Shakky `Trade` (magic-number-filtered by the caller).
        other_strategy_average_r_multiple: `{strategy_name: average_r_multiple}`
            for strategies other than Shakky, if available (from
            `src.interfaces.web.strategy_performance_service.
            get_strategy_performance`) -- used only for `better_strategy`.
            None/empty honestly skips that comparison rather than guessing.

    Returns:
        A `ShakkyLearningVerdict`.
    """
    if (
        trade.entry_price is None
        or trade.exit_price is None
        or trade.initial_stop_loss is None
        or trade.take_profit is None
    ):
        return ShakkyLearningVerdict(reasons=["insufficient_trade_data"])

    reasons: list[str] = []
    risk_distance = abs(trade.entry_price - trade.initial_stop_loss)
    target_distance = abs(trade.take_profit - trade.entry_price)
    mfe = trade.max_favorable_excursion or 0.0

    tp_too_small = target_distance > 0 and mfe > target_distance * (
        1 + _MEANINGFUL_MFE_EXCESS_FRACTION
    )
    if tp_too_small:
        reasons.append(
            f"mfe={mfe:.2f}_exceeds_target_distance={target_distance:.2f}_by_over_"
            f"{_MEANINGFUL_MFE_EXCESS_FRACTION:.0%}"
        )

    exit_near_target = (
        target_distance > 0
        and risk_distance > 0
        and (
            abs(trade.exit_price - trade.take_profit) <= risk_distance * _TP_HIT_TOLERANCE_FRACTION
        )
    )
    tp_too_large = (
        not exit_near_target
        and (trade.realized_pnl or 0.0) <= 0
        and mfe >= risk_distance * _MEANINGFUL_MFE_FOR_REVERSAL_FRACTION
    )
    if tp_too_large:
        reasons.append(
            f"mfe={mfe:.2f}_reached_{_MEANINGFUL_MFE_FOR_REVERSAL_FRACTION:.0%}_of_risk_"
            "but_trade_reversed_before_target"
        )

    r_multiple = _r_multiple(trade)
    should_have_scaled = (
        trade.entry_trend_confidence_score is not None
        and not trade.scale_events
        and r_multiple is not None
        and r_multiple >= _STRONG_R_MULTIPLE_FOR_SHOULD_HAVE_SCALED
    )
    if should_have_scaled:
        reasons.append(f"r_multiple={r_multiple:.2f}_with_no_scale_in")

    better_strategy = None
    if other_strategy_average_r_multiple and r_multiple is not None:
        own_strategy = classify_strategy(trade.department_votes)
        candidates = {
            name: avg
            for name, avg in other_strategy_average_r_multiple.items()
            if name != own_strategy
        }
        if candidates:
            best_name, best_avg = max(candidates.items(), key=lambda item: item[1])
            if best_avg > r_multiple:
                better_strategy = best_name
                reasons.append(
                    f"{best_name}_averages_{best_avg:.2f}R_overall_vs_{r_multiple:.2f}R_this_trade"
                )

    return ShakkyLearningVerdict(
        tp_too_small=tp_too_small,
        tp_too_large=tp_too_large,
        should_have_scaled=should_have_scaled,
        better_strategy=better_strategy,
        reasons=reasons,
    )


def other_strategy_average_r_multiple(
    closed_trades: list[Trade], *, own_strategy: str = "Shakky"
) -> dict[str, float]:
    """Average realized R-multiple per strategy other than `own_strategy`.

    Reuses `build_performance_report`'s existing `average_r_multiple`
    (already used platform-wide for "Strategy Ranking") rather than a
    second, parallel R-multiple computation -- `review_shakky_trade`'s
    `better_strategy` comparison intentionally accepts this being a
    slightly different R-multiple convention from its own (which
    measures against `initial_stop_loss` specifically) than one based
    on `Trade.stop_loss` at close time; both are legitimate R-multiple
    definitions, and the comparison is a heuristic hint, not a precise claim.

    Args:
        closed_trades: Every closed trade to consider (any strategy mix).
        own_strategy: The strategy to exclude from the result (Shakky's
            own trades don't need to be "compared against themselves").

    Returns:
        `{strategy_name: average_r_multiple}` for every other strategy
        with at least one reviewable closed trade.
    """
    grouped: dict[str, list[Trade]] = {}
    for trade in closed_trades:
        strategy = classify_strategy(trade.department_votes)
        if strategy != own_strategy and strategy != "unknown":
            grouped.setdefault(strategy, []).append(trade)
    return {
        name: report.average_r_multiple
        for name, group in grouped.items()
        if (report := build_performance_report(group)).trade_count > 0
    }
