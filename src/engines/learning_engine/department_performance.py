"""Department performance analysis for the Self Learning Engine.

Measures each department's realized directional accuracy from closed
trades that recorded a `Trade.department_votes` snapshot at signal time
(see `src.services.scheduler.live_loop._snapshot_department_votes`) —
"Automatically learn which components deserve more weight over time."

Per this project's governance ("No production strategy may change
automatically. All proposed strategy updates must be presented for user
approval"), this module only measures and reports a reliability score; it
does not write anything back into the live decision pipeline's confidence
weighting on its own. Wiring a validated score back into
`src.engines.statistics_engine.confidence.ConfidenceInput.historical_reliability`
is a separate, explicit step — matching how Phase 14's Hypothesis/
Improvement Proposal system already gates every other learned adjustment
behind explicit review, rather than silently reweighting production decisions.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.engines.learning_engine.factor_analysis import (
    OPINION_DEPARTMENTS,
    department_direction,
    outcome_direction,
)
from src.models.trade import Trade

# Below this many measured calls, a department's accuracy is not yet
# statistically meaningful; its reliability defaults to 1.0 (no
# adjustment), matching `ConfidenceInput.historical_reliability`'s own
# default until enough evidence exists.
_MIN_CALLS_FOR_RELIABILITY = 10
_DEFAULT_RELIABILITY = 1.0


@dataclass(frozen=True, slots=True)
class DepartmentPerformance:
    """One department's measured directional accuracy across closed trades.

    Per the "Performance Validation Framework" production requirement:
    "Prediction Accuracy, Contribution to winning trades, Contribution to
    losing trades, False Positive Rate, False Negative Rate."

    Attributes:
        department_name: The department's name, e.g. "technical", "correlation".
        total_calls: Number of closed trades where this department cast a
            non-neutral directional vote.
        correct_calls: Number of those calls where the department's
            direction matched the direction price actually moved.
        accuracy: `correct_calls / total_calls`, or 0.0 if `total_calls == 0`.
        reliability_score: `accuracy` if `total_calls >=
            _MIN_CALLS_FOR_RELIABILITY`, else the neutral default `1.0` —
            never a confident score from too little evidence.
        win_contribution_rate: Of all winning trades this department had a
            recorded vote for, the fraction where its vote agreed with the
            trade's own (winning) direction -- "how often was this
            department part of the winning consensus." 0.0 if there are
            no winning trades with a vote from this department.
        loss_contribution_rate: The same, but for losing trades -- "how
            often was this department part of the consensus behind a
            losing trade." 0.0 if there are no losing trades with a vote
            from this department.
        false_positive_rate: `1 - accuracy` -- the fraction of this
            department's non-neutral calls that pointed the wrong way.
        false_negative_rate: Of every closed trade in the input (whether
            or not this department had a recorded vote), the fraction
            where this department's vote was entirely absent from
            `Trade.department_votes` -- e.g. an unconfigured Macro/News
            provider at signal time. Distinct from a recorded "neutral"
            vote, which is a legitimate epistemic stance, not a gap.
            Caveat: for "scalping_engine"/"swing_engine"/"shakky_engine"
            (which only ever vote on their own strategy's own trades by
            design, not on every trade), this rate is naturally high and
            reflects that design, not a data gap -- meaningful mainly for
            the always-eligible departments (technical, historical, ml,
            macro, news, correlation, order_flow).
    """

    department_name: str
    total_calls: int
    correct_calls: int
    accuracy: float
    reliability_score: float
    win_contribution_rate: float = 0.0
    loss_contribution_rate: float = 0.0
    false_positive_rate: float = 0.0
    false_negative_rate: float = 0.0


def compute_department_reliability(
    closed_trades: list[Trade],
) -> dict[str, DepartmentPerformance]:
    """Compute each department's realized directional accuracy.

    Args:
        closed_trades: `Trade` rows with `status == "closed"`, ideally
            with `department_votes` recorded at signal time. Trades
            missing either field are skipped for the departments they
            would have contributed to — never fabricating a call.

    Returns:
        A `DepartmentPerformance` per department in
        `src.engines.learning_engine.factor_analysis.OPINION_DEPARTMENTS`,
        keyed by name — including departments never once seen in
        `closed_trades`, so `false_negative_rate` honestly reflects a
        department that never voted at all, not just one that
        occasionally votes incorrectly.
    """
    reviewable = [trade for trade in closed_trades if outcome_direction(trade) is not None]
    total_reviewable = len(reviewable)

    # name -> [correct, total, wins_agreed, total_wins, losses_agreed, total_losses, absent_count]
    tallies: dict[str, list[int]] = {name: [0, 0, 0, 0, 0, 0, 0] for name in OPINION_DEPARTMENTS}

    for trade in reviewable:
        trade_outcome_direction = outcome_direction(trade)
        is_win = (trade.realized_pnl or 0.0) > 0
        votes = trade.department_votes or {}

        for name in OPINION_DEPARTMENTS:
            tally = tallies[name]
            if name not in votes:
                tally[6] += 1  # absent_count
                continue

            if is_win:
                tally[3] += 1  # total_wins
            else:
                tally[5] += 1  # total_losses

            vote_direction = department_direction(votes[name].get("bias"))
            if vote_direction is None:
                continue  # a recorded but neutral vote: present, not a directional call

            tally[1] += 1  # total
            if vote_direction == trade_outcome_direction:
                tally[0] += 1  # correct
                if is_win:
                    tally[2] += 1  # wins_agreed
            elif not is_win:
                tally[4] += 1  # losses_agreed

    results: dict[str, DepartmentPerformance] = {}
    for name, (
        correct,
        total,
        wins_agreed,
        total_wins,
        losses_agreed,
        total_losses,
        absent_count,
    ) in tallies.items():
        accuracy = correct / total if total > 0 else 0.0
        reliability = accuracy if total >= _MIN_CALLS_FOR_RELIABILITY else _DEFAULT_RELIABILITY
        results[name] = DepartmentPerformance(
            department_name=name,
            total_calls=total,
            correct_calls=correct,
            accuracy=accuracy,
            reliability_score=reliability,
            win_contribution_rate=(wins_agreed / total_wins if total_wins > 0 else 0.0),
            loss_contribution_rate=(losses_agreed / total_losses if total_losses > 0 else 0.0),
            false_positive_rate=(1.0 - accuracy) if total > 0 else 0.0,
            false_negative_rate=(absent_count / total_reviewable if total_reviewable > 0 else 0.0),
        )
    return results


def compute_department_reliability_scores(closed_trades: list[Trade]) -> dict[str, float]:
    """Compute each department's `reliability_score` alone, for weighting live decisions.

    Per the "Trade Quality Engine" production requirement: "Chief AI must
    combine these using calibrated weights instead of simple averaging."
    This is the thin adapter between `compute_department_reliability`'s
    full measurement and the plain `{name: weight}` shape
    `src.engines.statistics_engine.probability.combine_department_votes`
    and `src.engines.statistics_engine.confidence.ConfidenceInput` expect.

    Args:
        closed_trades: `Trade` rows with `status == "closed"`.

    Returns:
        `{department_name: reliability_score}`. A department absent here
        (never yet measured) should fall back to the neutral default
        weight at the call site, not be treated as zero.
    """
    return {
        name: performance.reliability_score
        for name, performance in compute_department_reliability(closed_trades).items()
    }
