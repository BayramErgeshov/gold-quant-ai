"""Automatic post-trade analysis for every closed trade (Self Learning Engine).

Per the "Post Trade Analysis" production requirement: every closed trade
-- win or loss -- automatically answers "Would Chief AI open this trade
again, knowing the final outcome?" The verdict is judged on entry
*process* quality (department agreement/disagreement recorded at signal
time), not on the realized P&L sign: a loss with strong, aligned evidence
at entry still earns a YES ("the logic was still correct"); a win with
2+ departments opposing the entry still earns a NO ("what was missed"),
since the process could equally have lost. This module never modifies
trading logic — it only produces a report and, once a mistake factor
recurs across multiple losing trades specifically, a pending
`ImprovementProposal` requiring explicit human approval (CLAUDE.md: "No
production strategy may change automatically").
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.engines.learning_engine.factor_analysis import (
    TradeFactor,
    analyze_department_disagreement,
    department_correctness,
    disagreeing_departments,
    missing_departments,
)
from src.engines.learning_engine.hypothesis import generate_hypotheses_from_factors
from src.engines.learning_engine.proposal import build_proposal_from_hypothesis
from src.engines.learning_engine.trade_review import TradeReview, review_closed_trade
from src.models.trade import Trade
from src.repositories.improvement_proposal_repository import ImprovementProposalRepository
from src.repositories.trade_repository import TradeRepository

# 2+ opposing departments at entry is treated as strong enough evidence
# that the trade likely should not have executed — a factual, threshold
# based flag, not a fabricated verdict.
_SKIP_RECOMMENDATION_DISAGREEMENT_THRESHOLD = 2

_MIN_OCCURRENCES_FOR_PROPOSAL = 3


@dataclass(frozen=True, slots=True)
class PostMortemReport:
    """A single closed trade's automatic post-trade analysis.

    Attributes:
        trade_id: The reviewed trade's id.
        review: Realized-outcome metrics (return, R-multiple, holding time).
        factors: Every measurable mistake factor identified (missing- and
            disagreeing-department factors; entry-quality factors from
            `analyze_losing_trade` if the caller supplies a `TradeContext`
            separately — this report only covers what is derivable from
            the persisted `Trade` row alone).
        disagreeing_departments: Departments whose recorded vote opposed
            this trade's own direction — "which AI agents disagreed."
        missing_departments: Opinion departments with no recorded vote
            for this trade — "what external information was missing."
        department_correctness: `{department_name: was_correct}`, judged
            against the REALIZED outcome (not the entry direction) --
            "which AI agents were actually right or wrong," per the "Post
            Trade Learning" production requirement. Distinct from
            `disagreeing_departments`, which only reflects entry-time
            agreement with the trade's own direction.
        should_have_been_skipped: True once enough departments opposed
            the entry that it likely should not have executed.
        would_repeat: The "Post Trade Analysis" verdict: would Chief AI
            open this trade again, knowing the outcome? Judged on entry
            process quality (`not should_have_been_skipped`), independent
            of the realized P&L sign — never a fabricated hindsight claim
            about the outcome itself. Russian phrasing of the verdict and
            its supporting reasons is built at the display boundary
            (`src.core.notifications.formatting.format_post_mortem_message`)
            from this field plus `disagreeing_departments`/
            `missing_departments`, per this codebase's convention of
            translating internal data to Russian only at that boundary.
    """

    trade_id: str
    review: TradeReview
    factors: list[TradeFactor] = field(default_factory=list)
    disagreeing_departments: list[str] = field(default_factory=list)
    missing_departments: list[str] = field(default_factory=list)
    department_correctness: dict[str, bool] = field(default_factory=dict)
    should_have_been_skipped: bool = False
    would_repeat: bool = True


def generate_post_mortem(trade: Trade) -> PostMortemReport:
    """Build a `PostMortemReport` from a closed trade's own recorded fields.

    Args:
        trade: A closed `Trade`.

    Returns:
        The derived `PostMortemReport`, covering both wins and losses.
    """
    review = review_closed_trade(trade)
    disagreement_factors = analyze_department_disagreement(trade)
    missing = missing_departments(trade)
    should_have_been_skipped = (
        len(disagreement_factors) >= _SKIP_RECOMMENDATION_DISAGREEMENT_THRESHOLD
    )

    return PostMortemReport(
        trade_id=str(trade.id),
        review=review,
        factors=[
            *disagreement_factors,
            *(
                TradeFactor(
                    name=f"missing_department_evidence:{name}", detail=f"{name!r} had no vote."
                )
                for name in missing
            ),
        ],
        disagreeing_departments=disagreeing_departments(trade),
        missing_departments=missing,
        department_correctness=department_correctness(trade),
        should_have_been_skipped=should_have_been_skipped,
        would_repeat=not should_have_been_skipped,
    )


class PostMortemService:
    """Runs every closed trade's post-trade analysis and proposes fixes for recurring losses."""

    def __init__(
        self,
        *,
        trade_repository: TradeRepository,
        proposal_repository: ImprovementProposalRepository,
        min_occurrences_for_proposal: int = _MIN_OCCURRENCES_FOR_PROPOSAL,
    ) -> None:
        """Initialize the service (constructor injection).

        Args:
            trade_repository: Source of every closed trade, used to scan
                for recurring mistake factors across losing trades.
            proposal_repository: Persists pending improvement proposals
                and de-duplicates them by title.
            min_occurrences_for_proposal: How many losing trades must
                share a mistake factor before it becomes a proposal — a
                single trade is an anecdote, never a hypothesis
                (RESEARCH_FRAMEWORK.md).
        """
        self._trades = trade_repository
        self._proposals = proposal_repository
        self._min_occurrences = min_occurrences_for_proposal

    async def run_for_closed_trade(self, trade: Trade) -> PostMortemReport:
        """Run the full post-trade analysis pipeline for one newly-closed trade.

        Per the "Post Trade Analysis" production requirement: every
        closed trade -- win or loss -- gets a report; recurring-mistake
        proposals are still scanned only across losing trades (a winning
        trade is never itself the basis for a "mistake" proposal).

        Args:
            trade: The closed `Trade` to review.

        Returns:
            The `PostMortemReport`.
        """
        report = generate_post_mortem(trade)
        if (trade.realized_pnl or 0.0) < 0:
            await self._propose_improvement_if_recurring(report.factors)
        return report

    async def _propose_improvement_if_recurring(self, new_factors: list[TradeFactor]) -> None:
        if not new_factors:
            return

        losing_trades = [
            t
            for t in await self._trades.list_by_status("closed", limit=100)
            if (t.realized_pnl or 0.0) < 0
        ]
        all_factors = [
            factor
            for losing_trade in losing_trades
            for factor in generate_post_mortem(losing_trade).factors
        ]

        for hypothesis in generate_hypotheses_from_factors(
            all_factors, min_occurrences=self._min_occurrences
        ):
            if await self._proposals.exists_with_title(hypothesis.question):
                continue
            proposal = build_proposal_from_hypothesis(
                hypothesis,
                historical_statistics={"recurring_losing_trades": float(len(losing_trades))},
                validation_results={},
                potential_risk=(
                    "Not yet backtested — this proposal only reflects a recurring pattern "
                    "across live losing trades and requires validation before approval."
                ),
            )
            await self._proposals.add(proposal)
