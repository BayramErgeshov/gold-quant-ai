"""Improvement proposal construction for the Self Learning Engine.

Per SELF_LEARNING_ENGINE.md "Improvement Proposals": "Every proposal must
include Problem, Evidence, Historical Statistics, Expected Benefit,
Potential Risk, Implementation Difficulty, Validation Results,
Recommendation, User Approval Required." Every proposal this builder
produces starts `status="pending"` — nothing in this codebase approves a
proposal automatically (SELF_LEARNING_ENGINE.md "User Approval").
"""

from __future__ import annotations

from src.engines.learning_engine.hypothesis import Hypothesis
from src.models.improvement_proposal import ImprovementProposal


def build_proposal_from_hypothesis(
    hypothesis: Hypothesis,
    *,
    historical_statistics: dict[str, float],
    validation_results: dict[str, float],
    potential_risk: str,
    implementation_difficulty: str = "medium",
) -> ImprovementProposal:
    """Build a pending `ImprovementProposal` from a validated hypothesis.

    Args:
        hypothesis: The hypothesis this proposal addresses.
        historical_statistics: Measured statistics backing the proposal
            (e.g. win rate/profit factor observed in the reviewed trades).
        validation_results: Backtest/walk-forward/Monte Carlo results
            supporting the proposal.
        potential_risk: Known risks of implementing this change.
        implementation_difficulty: One of
            `src.models.improvement_proposal.IMPLEMENTATION_DIFFICULTIES`.

    Returns:
        A new `ImprovementProposal` with `status="pending"`, ready to be
        persisted via `ImprovementProposalRepository.add` and surfaced for
        user review — never auto-approved.
    """
    return ImprovementProposal(
        title=hypothesis.question,
        problem=hypothesis.motivation,
        evidence=hypothesis.supporting_evidence,
        historical_statistics=historical_statistics,
        expected_benefit=hypothesis.expected_outcome,
        potential_risk=potential_risk,
        implementation_difficulty=implementation_difficulty,
        validation_results=validation_results,
        recommendation=(
            f"{hypothesis.validation_plan} Success criteria: {hypothesis.success_criteria} "
            f"Failure criteria: {hypothesis.failure_criteria}"
        ),
        status="pending",
    )
