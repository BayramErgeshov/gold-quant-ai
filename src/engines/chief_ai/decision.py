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
)
_CONFLICT_MARGIN = 0.1


@dataclass(frozen=True, slots=True)
class ChiefAIInput:
    """Every evidence source the Chief AI evaluates for one decision cycle.

    Attributes:
        department_votes: Each department's own `CombinedVote` (e.g.
            "technical", "macro", "news", "historical", "ml").
        reports_present: Which `REQUIRED_REPORTS` were successfully
            produced this cycle (DECISION_ENGINE.md "Required Inputs"). A
            missing report forces WAIT regardless of everything else.
        risk_decision: The Risk Engine's `TradeApprovalDecision` for this
            candidate trade.
        confidence_threshold: Minimum overall confidence (0-100) required to BUY/SELL.
        market_regime: Current classified regime, if known
            (`src.engines.historical_engine.regime_detection`).
        critical_news_imminent: Increases uncertainty and can force WAIT.
    """

    department_votes: dict[str, CombinedVote]
    reports_present: dict[str, bool]
    risk_decision: TradeApprovalDecision
    confidence_threshold: float = 70.0
    market_regime: str | None = None
    critical_news_imminent: bool = False


@dataclass(frozen=True, slots=True)
class ChiefAIDecision:
    """The Chief AI's final institutional decision.

    Attributes:
        state: One of `DecisionState`.
        probability: The combined cross-department probability distribution.
        confidence_pct: Overall confidence, in [0.0, 100.0].
        uncertainty_factors: Every factor increasing uncertainty this cycle
            (DECISION_ENGINE.md "Uncertainty").
        reasons: Why this `state` was chosen.
        supporting_evidence: Pooled supporting evidence across departments.
        opposing_evidence: Pooled opposing evidence across departments.
    """

    state: DecisionState
    probability: ProbabilityEstimate
    confidence_pct: float
    uncertainty_factors: list[str]
    reasons: list[str]
    supporting_evidence: list[str] = field(default_factory=list)
    opposing_evidence: list[str] = field(default_factory=list)


def _missing_reports(reports_present: dict[str, bool]) -> list[str]:
    return [name for name in REQUIRED_REPORTS if not reports_present.get(name, False)]


def _detect_conflict(probability: ProbabilityEstimate) -> bool:
    return abs(probability.bullish_probability - probability.bearish_probability) < (
        _CONFLICT_MARGIN
    )


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
    if missing:
        return ChiefAIDecision(
            state="WAIT",
            probability=ProbabilityEstimate(
                bullish_probability=0.0, bearish_probability=0.0, neutral_probability=1.0
            ),
            confidence_pct=0.0,
            uncertainty_factors=[f"missing_report:{name}" for name in missing],
            reasons=["required_report_missing"],
        )

    probability = combine_department_votes(chief_input.department_votes)
    confidence_inputs = [
        ConfidenceInput(name=name, confidence=vote.confidence * 100)
        for name, vote in chief_input.department_votes.items()
    ]
    confidence_pct = compute_overall_confidence(confidence_inputs)
    supporting_evidence, opposing_evidence = _pooled_evidence(chief_input.department_votes)

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
    )
