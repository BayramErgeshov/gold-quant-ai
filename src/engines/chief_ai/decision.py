"""Chief AI decision orchestration.

Per DECISION_ENGINE.md: the final institutional decision layer. It never
performs research and never executes trades — it only evaluates evidence
already produced by every department (Technical, Macro, News, Historical,
ML, Statistics) and the Risk Engine's approval, and determines whether a
trade should exist. "The default decision is always WAIT."
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from src.core.agents.confluence import CombinedVote
from src.engines.chief_ai.trade_quality import TradeQualityResult, compute_trade_quality
from src.engines.risk_engine.approval import TradeApprovalDecision
from src.engines.statistics_engine.confidence import ConfidenceInput, compute_overall_confidence
from src.engines.statistics_engine.probability import ProbabilityEstimate, combine_department_votes

DecisionState = Literal[
    "BUY", "SELL", "WAIT", "NO_TRADE", "RESEARCH_MORE", "REDUCE_EXPOSURE", "EMERGENCY_EXIT"
]

REQUIRED_REPORTS: tuple[str, ...] = (
    "technical",
    "macro",
    "news",
    "historical",
    "ml",
    "statistics",
    "risk",
    "execution",
    "correlation",
    "order_flow",
)
_CONFLICT_MARGIN = 0.1
# Per AGENT_SYSTEM.md "never trust a single source": a decision made without
# every independent confirming department is inherently less reliable, even
# when it is still allowed to proceed (see `ChiefAIInput.optional_reports`).
# This is a fixed, documented discount rather than a fabricated precise
# number; it exists so fewer-source decisions are harder to clear the
# confidence threshold, not a claim about the exact reliability cost.
_REDUCED_CONFIDENCE_DISCOUNT = 0.85


@dataclass(frozen=True, slots=True)
class ChiefAIInput:
    """Every evidence source the Chief AI evaluates for one decision cycle.

    Attributes:
        department_votes: Each department's own `CombinedVote` (e.g.
            "technical", "macro", "news", "historical", "ml",
            "correlation", "order_flow").
        reports_present: Which `REQUIRED_REPORTS` were successfully
            produced this cycle (DECISION_ENGINE.md "Required Inputs"). A
            missing report forces WAIT unless it is listed in
            `optional_reports`.
        risk_decision: The Risk Engine's `TradeApprovalDecision` for this
            candidate trade.
        confidence_threshold: Minimum overall confidence (0-100) required to BUY/SELL.
        market_regime: Current classified regime, if known
            (`src.engines.historical_engine.regime_detection`).
        critical_news_imminent: Increases uncertainty and can force WAIT.
        optional_reports: Reports that, if missing, do not force WAIT —
            instead the decision is flagged `reduced_confidence` and its
            confidence is discounted. Used when a department's external
            data source is not yet configured (e.g. Macro/News before
            FRED/NewsAPI keys are added) rather than blocking every
            decision indefinitely; still never fabricates the missing
            department's opinion.
        department_reliability: Each department's measured historical
            accuracy (`src.engines.learning_engine.department_performance`),
            keyed by department name. Used as the weight for both the
            cross-department probability combination and the overall
            confidence calculation -- "calibrated weights instead of
            simple averaging" (Trade Quality Engine production
            requirement) -- and for the Trade Quality Score's reliability
            component. A department absent here defaults to the neutral
            weight of 1.0.
        books_confluence: How much statistically-validated book knowledge
            (`src.repositories.book_claim_repository`) supports this
            setup, in [0.0, 1.0]. Defaults to 0.0 -- never fabricated
            support before any claim has actually been validated.
        min_trade_quality_score: Minimum Trade Quality Score (0-100)
            required to BUY/SELL, per the "Trade Quality Engine"
            production requirement: the score becomes the primary
            decision metric, not just a displayed number. 0.0 means no
            additional gate beyond `confidence_threshold`.
    """

    department_votes: dict[str, CombinedVote]
    reports_present: dict[str, bool]
    risk_decision: TradeApprovalDecision
    confidence_threshold: float = 70.0
    market_regime: str | None = None
    critical_news_imminent: bool = False
    optional_reports: frozenset[str] = frozenset()
    department_reliability: dict[str, float] = field(default_factory=dict)
    books_confluence: float = 0.0
    min_trade_quality_score: float = 0.0


@dataclass(frozen=True, slots=True)
class ChiefAIDecision:
    """The Chief AI's final institutional decision.

    Attributes:
        state: One of `DecisionState`.
        probability: The combined cross-department probability distribution.
        confidence_pct: Overall confidence, in [0.0, 100.0] — already
            discounted if `reduced_confidence_factors` is non-empty.
        uncertainty_factors: Every factor increasing uncertainty this cycle
            (DECISION_ENGINE.md "Uncertainty"). Non-empty always forces WAIT.
        reasons: Why this `state` was chosen.
        supporting_evidence: Pooled supporting evidence across departments.
        opposing_evidence: Pooled opposing evidence across departments.
        reduced_confidence_factors: Optional reports that were unavailable
            this cycle (`ChiefAIInput.optional_reports`). Non-empty means
            this decision was made with fewer independent sources than
            the platform's full design calls for — flagged, but does not
            by itself force WAIT.
        trade_quality: The Trade Quality Engine's 0-100 score, risk score
            and reasoning for this cycle (`src.engines.chief_ai.trade_quality`).
            Always computed, even for a WAIT decision, so a near-miss
            setup's quality is still visible.
    """

    state: DecisionState
    probability: ProbabilityEstimate
    confidence_pct: float
    uncertainty_factors: list[str]
    reasons: list[str]
    supporting_evidence: list[str] = field(default_factory=list)
    opposing_evidence: list[str] = field(default_factory=list)
    reduced_confidence_factors: list[str] = field(default_factory=list)
    trade_quality: TradeQualityResult = field(
        default_factory=lambda: TradeQualityResult(score=0.0, risk_score=0.0)
    )

    @property
    def is_reduced_confidence(self) -> bool:
        """Whether this decision was made with an optional report missing."""
        return bool(self.reduced_confidence_factors)


def _missing_reports(reports_present: dict[str, bool]) -> list[str]:
    return [name for name in REQUIRED_REPORTS if not reports_present.get(name, False)]


def _detect_conflict(probability: ProbabilityEstimate) -> bool:
    return abs(probability.bullish_probability - probability.bearish_probability) < (
        _CONFLICT_MARGIN
    )


def compute_department_confidence(
    department_votes: dict[str, CombinedVote],
    *,
    reduced_confidence_factors: list[str],
    department_reliability: dict[str, float] | None = None,
) -> float:
    """Compute overall confidence from department votes (DECISION_ENGINE.md).

    Extracted so callers building a `ChiefAIInput.risk_decision` ahead of
    `evaluate()` (e.g. the Market Update Workflow) can derive the same
    confidence score the Trade Approval Pipeline gates on, rather than
    duplicating this calculation (CODING_STANDARDS.md "Never duplicate
    functionality").

    Args:
        department_votes: Each department's own `CombinedVote`.
        reduced_confidence_factors: Non-empty when an optional report was
            unavailable this cycle; discounts the result identically to
            `evaluate()`.
        department_reliability: Each department's measured historical
            accuracy, keyed by name (see `ChiefAIInput.department_reliability`).
            A department absent here defaults to the neutral weight of
            1.0 -- "calibrated weights instead of simple averaging"
            (Trade Quality Engine production requirement).

    Returns:
        Overall confidence in [0.0, 100.0].
    """
    resolved_reliability = department_reliability or {}
    confidence_inputs = [
        ConfidenceInput(
            name=name,
            confidence=vote.confidence * 100,
            historical_reliability=resolved_reliability.get(name, 1.0),
        )
        for name, vote in department_votes.items()
    ]
    confidence_pct = compute_overall_confidence(confidence_inputs)
    if reduced_confidence_factors:
        confidence_pct *= _REDUCED_CONFIDENCE_DISCOUNT
    return confidence_pct


def _pooled_evidence(
    department_votes: dict[str, CombinedVote],
) -> tuple[list[str], list[str]]:
    supporting = sorted(
        {
            evidence
            for vote in department_votes.values()
            for evidence in vote.strongest_supporting_factors
        }
    )
    opposing = sorted(
        {
            evidence
            for vote in department_votes.values()
            for evidence in vote.strongest_opposing_factors
        }
    )
    return supporting, opposing


def evaluate(chief_input: ChiefAIInput) -> ChiefAIDecision:
    """Run the DECISION_ENGINE.md "Decision Pipeline" and produce a final decision.

    Args:
        chief_input: Every evidence source for this decision cycle.

    Returns:
        A `ChiefAIDecision`. Defaults to WAIT whenever evidence is
        incomplete, conflicting, low-confidence, or Risk-rejected — per
        DECISION_ENGINE.md "The default decision is always WAIT."
    """
    missing = _missing_reports(chief_input.reports_present)
    hard_missing = [name for name in missing if name not in chief_input.optional_reports]
    if hard_missing:
        empty_probability = ProbabilityEstimate(
            bullish_probability=0.0, bearish_probability=0.0, neutral_probability=1.0
        )
        return ChiefAIDecision(
            state="WAIT",
            probability=empty_probability,
            confidence_pct=0.0,
            uncertainty_factors=[f"missing_report:{name}" for name in hard_missing],
            reasons=["required_report_missing"],
            trade_quality=compute_trade_quality(
                probability=empty_probability,
                confidence_pct=0.0,
                department_votes=chief_input.department_votes,
                department_reliability=chief_input.department_reliability,
                books_confluence=chief_input.books_confluence,
            ),
        )
    reduced_confidence_factors = [
        f"reduced_confidence:{name}_unavailable"
        for name in missing
        if name in chief_input.optional_reports
    ]

    probability = combine_department_votes(
        chief_input.department_votes, weights=chief_input.department_reliability or None
    )
    confidence_pct = compute_department_confidence(
        chief_input.department_votes,
        reduced_confidence_factors=reduced_confidence_factors,
        department_reliability=chief_input.department_reliability,
    )
    supporting_evidence, opposing_evidence = _pooled_evidence(chief_input.department_votes)
    trade_quality = compute_trade_quality(
        probability=probability,
        confidence_pct=confidence_pct,
        department_votes=chief_input.department_votes,
        department_reliability=chief_input.department_reliability,
        books_confluence=chief_input.books_confluence,
    )

    uncertainty_factors: list[str] = []
    if chief_input.critical_news_imminent:
        uncertainty_factors.append("critical_news_imminent")
    if _detect_conflict(probability):
        uncertainty_factors.append("conflicting_departments")
    if chief_input.market_regime is None:
        uncertainty_factors.append("unknown_market_regime")

    if not chief_input.risk_decision.approved:
        return ChiefAIDecision(
            state="WAIT",
            probability=probability,
            confidence_pct=confidence_pct,
            uncertainty_factors=uncertainty_factors,
            reasons=[
                f"risk_rejected:{reason}" for reason in chief_input.risk_decision.rejection_reasons
            ],
            supporting_evidence=supporting_evidence,
            opposing_evidence=opposing_evidence,
            reduced_confidence_factors=reduced_confidence_factors,
            trade_quality=trade_quality,
        )

    if confidence_pct < chief_input.confidence_threshold:
        return ChiefAIDecision(
            state="WAIT",
            probability=probability,
            confidence_pct=confidence_pct,
            uncertainty_factors=uncertainty_factors,
            reasons=[
                f"confidence_below_threshold: {confidence_pct:.1f} < "
                f"{chief_input.confidence_threshold}"
            ],
            supporting_evidence=supporting_evidence,
            opposing_evidence=opposing_evidence,
            reduced_confidence_factors=reduced_confidence_factors,
            trade_quality=trade_quality,
        )

    # Per the "Trade Quality Engine" production requirement: the score
    # is the primary decision metric, not merely displayed -- a trade
    # below this floor is rejected even though confidence alone cleared
    # `confidence_threshold` above.
    if trade_quality.score < chief_input.min_trade_quality_score:
        return ChiefAIDecision(
            state="WAIT",
            probability=probability,
            confidence_pct=confidence_pct,
            uncertainty_factors=uncertainty_factors,
            reasons=[
                f"trade_quality_below_threshold: {trade_quality.score:.1f} < "
                f"{chief_input.min_trade_quality_score}"
            ],
            supporting_evidence=supporting_evidence,
            opposing_evidence=opposing_evidence,
            reduced_confidence_factors=reduced_confidence_factors,
            trade_quality=trade_quality,
        )

    if uncertainty_factors:
        return ChiefAIDecision(
            state="WAIT",
            probability=probability,
            confidence_pct=confidence_pct,
            uncertainty_factors=uncertainty_factors,
            reasons=list(uncertainty_factors),
            supporting_evidence=supporting_evidence,
            opposing_evidence=opposing_evidence,
            reduced_confidence_factors=reduced_confidence_factors,
            trade_quality=trade_quality,
        )

    if probability.bullish_probability > probability.bearish_probability:
        state: DecisionState = "BUY"
        reasons = ["bullish_probability_exceeds_bearish", "risk_approved", "confidence_sufficient"]
    elif probability.bearish_probability > probability.bullish_probability:
        state = "SELL"
        reasons = ["bearish_probability_exceeds_bullish", "risk_approved", "confidence_sufficient"]
    else:  # pragma: no cover - unreachable: equal probabilities is always a detected conflict
        state = "WAIT"
        reasons = ["probability_tied"]

    return ChiefAIDecision(
        state=state,
        probability=probability,
        confidence_pct=confidence_pct,
        uncertainty_factors=uncertainty_factors,
        reasons=reasons,
        supporting_evidence=supporting_evidence,
        opposing_evidence=opposing_evidence,
        reduced_confidence_factors=reduced_confidence_factors,
        trade_quality=trade_quality,
    )
