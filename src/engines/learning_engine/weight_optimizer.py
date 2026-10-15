"""AI Weight Optimizer for the Self Learning Engine.

Per the "AI Weight Optimizer" production requirement: "Create an
optimizer that does NOT automatically modify weights. Instead, analyze
every 100 completed trades and generate a recommendation showing Current
Weight, Suggested Weight, Reason... User must explicitly approve any
weight changes." This module only computes candidate recommendations
from already-closed trades -- nothing here writes to the database or
changes a live weight. See
`src.repositories.weight_recommendation_repository` for persistence and
`src.models.weight_recommendation.DepartmentWeightOverride` for the only
place an approved change actually takes effect.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from src.engines.learning_engine.department_performance import compute_department_reliability
from src.engines.learning_engine.factor_analysis import OPINION_DEPARTMENTS
from src.models.trade import Trade
from src.models.weight_recommendation import WeightRecommendation
from src.repositories.trade_repository import TradeRepository
from src.repositories.weight_recommendation_repository import WeightRecommendationRepository

TRADES_PER_BATCH = 100
# A change smaller than this many points of reliability (0-1 scale) is
# noise-level sampling variance, not worth surfacing as a recommendation.
_MATERIALITY_THRESHOLD = 0.02
# This research platform is nowhere near this many closed trades; a
# generous cap rather than true unbounded pagination, matching
# `src.interfaces.web.performance_service._MAX_CLOSED_TRADES_FOR_REPORT`'s
# own "read everything durable" approach -- batch slicing below needs the
# full chronological history, not just a recent window.
_MAX_CLOSED_TRADES_CONSIDERED = 5000


@dataclass(frozen=True, slots=True)
class WeightRecommendationDraft:
    """One department's proposed weight adjustment, not yet persisted.

    Attributes:
        department_name: The department this recommendation is for (see
            `src.engines.learning_engine.factor_analysis.OPINION_DEPARTMENTS`).
        trade_batch_number: Which consecutive `TRADES_PER_BATCH`-trade
            batch this recommendation covers (1 = trades 1-100, 2 =
            trades 1-200, ...).
        current_weight: Reliability score computed from every closed
            trade *before* this batch -- what has been driving live
            decisions up to now.
        suggested_weight: Reliability score computed from every closed
            trade *through* this batch, i.e. including the new evidence.
        reason: Short human-readable explanation of the direction and
            magnitude of the suggested change.
        supporting_stats: The batch's own measured accuracy/sample size
            behind this suggestion -- never a fabricated justification.
    """

    department_name: str
    trade_batch_number: int
    current_weight: float
    suggested_weight: float
    reason: str
    supporting_stats: dict[str, float | int] = field(default_factory=dict)


def _reason(department_name: str, current_weight: float, suggested_weight: float) -> str:
    direction = "Higher" if suggested_weight > current_weight else "Lower"
    return (
        f"{direction} predictive accuracy for {department_name} during the last "
        f"{TRADES_PER_BATCH} trades ({suggested_weight * 100:.0f}% vs. the prior "
        f"{current_weight * 100:.0f}%)."
    )


def generate_weight_recommendations(
    closed_trades_chronological: list[Trade], *, trade_batch_number: int
) -> list[WeightRecommendationDraft]:
    """Compare each department's weight before vs. through one completed 100-trade batch.

    Args:
        closed_trades_chronological: Every closed trade, oldest first.
            Must contain at least `trade_batch_number * TRADES_PER_BATCH`
            trades -- callers are responsible for only invoking this once
            a batch has actually completed.
        trade_batch_number: Which consecutive 100-trade batch to evaluate
            (1-indexed).

    Returns:
        One `WeightRecommendationDraft` per department whose reliability
        score moved by at least `_MATERIALITY_THRESHOLD` once this
        batch's evidence is included -- empty if every department's
        measured accuracy held steady.
    """
    batch_start = (trade_batch_number - 1) * TRADES_PER_BATCH
    batch_end = trade_batch_number * TRADES_PER_BATCH
    trades_before_batch = closed_trades_chronological[:batch_start]
    trades_through_batch = closed_trades_chronological[:batch_end]
    trades_in_this_batch = closed_trades_chronological[batch_start:batch_end]

    current_performance = compute_department_reliability(trades_before_batch)
    suggested_performance = compute_department_reliability(trades_through_batch)
    batch_only_performance = compute_department_reliability(trades_in_this_batch)

    recommendations: list[WeightRecommendationDraft] = []
    for name in OPINION_DEPARTMENTS:
        current_weight = current_performance[name].reliability_score
        suggested = suggested_performance[name]
        batch_only = batch_only_performance[name]
        if abs(suggested.reliability_score - current_weight) < _MATERIALITY_THRESHOLD:
            continue

        recommendations.append(
            WeightRecommendationDraft(
                department_name=name,
                trade_batch_number=trade_batch_number,
                current_weight=current_weight,
                suggested_weight=suggested.reliability_score,
                reason=_reason(name, current_weight, batch_only.accuracy),
                supporting_stats={
                    "batch_accuracy": batch_only.accuracy,
                    "batch_total_calls": batch_only.total_calls,
                    "batch_correct_calls": batch_only.correct_calls,
                },
            )
        )
    return recommendations


async def maybe_generate_recommendations(session: AsyncSession) -> list[WeightRecommendation]:
    """Generate and persist recommendations for the newest completed 100-trade batch, if due.

    Safe to call every live-loop cycle: if the closed-trade count hasn't
    crossed a new multiple of `TRADES_PER_BATCH` since the last call, or
    every department's weight already has a persisted recommendation for
    the current batch, this is a cheap no-op.

    Args:
        session: The active database session.

    Returns:
        Every newly persisted `WeightRecommendation` this call created --
        empty if no batch is due or nothing moved enough to recommend.
    """
    trade_repository = TradeRepository(session)
    recommendation_repository = WeightRecommendationRepository(session)

    total_closed = await trade_repository.count_by_status("closed")
    batch_number = total_closed // TRADES_PER_BATCH
    if batch_number < 1:
        return []

    closed_trades = await trade_repository.list_by_status(
        "closed", limit=_MAX_CLOSED_TRADES_CONSIDERED
    )
    chronological = sorted(closed_trades, key=lambda trade: trade.closed_at or trade.created_at)
    drafts = generate_weight_recommendations(chronological, trade_batch_number=batch_number)

    persisted: list[WeightRecommendation] = []
    for draft in drafts:
        already_recorded = await recommendation_repository.exists_for_batch(
            draft.department_name, draft.trade_batch_number
        )
        if already_recorded:
            continue
        persisted.append(
            await recommendation_repository.add(
                WeightRecommendation(
                    department_name=draft.department_name,
                    trade_batch_number=draft.trade_batch_number,
                    current_weight=draft.current_weight,
                    suggested_weight=draft.suggested_weight,
                    reason=draft.reason,
                    supporting_stats=draft.supporting_stats,
                )
            )
        )
    return persisted
