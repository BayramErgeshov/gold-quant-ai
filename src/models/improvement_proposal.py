"""ORM model for the improvement proposal system (DATABASE.md:
`improvement_proposals`; SELF_LEARNING_ENGINE.md "Improvement Proposals").

Per SELF_LEARNING_ENGINE.md "User Approval": "The system may NEVER change
production strategy, risk rules, execution logic [or] confidence
calculation without explicit user approval. It may only propose
improvements." Every row starts `status="pending"`; only an explicit user
action moves it to `approved`/`rejected` — nothing in this codebase
transitions a proposal automatically.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, CheckConstraint, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.database.postgres.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

IMPLEMENTATION_DIFFICULTIES: tuple[str, ...] = ("low", "medium", "high")
PROPOSAL_STATUSES: tuple[str, ...] = ("pending", "approved", "rejected")


class ImprovementProposal(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A single proposed, user-reviewable platform improvement.

    Attributes:
        title: Short human-readable summary.
        problem: The problem this proposal addresses.
        evidence: Supporting evidence for the problem's existence.
        historical_statistics: Measured statistics backing the proposal
            (e.g. win rate/profit factor before vs. after, in a backtest).
        expected_benefit: The anticipated improvement if approved.
        potential_risk: Known risks of implementing this change.
        implementation_difficulty: One of `IMPLEMENTATION_DIFFICULTIES`.
        validation_results: Backtest/walk-forward/Monte Carlo results
            supporting the proposal (SELF_LEARNING_ENGINE.md "Strategy Validation").
        recommendation: The engine's recommendation, for the user to weigh.
        status: One of `PROPOSAL_STATUSES`. Always starts "pending".
    """

    __tablename__ = "improvement_proposals"
    __table_args__ = (
        CheckConstraint(
            f"implementation_difficulty IN {IMPLEMENTATION_DIFFICULTIES}",
            name="ck_improvement_proposals_difficulty_valid",
        ),
        CheckConstraint(
            f"status IN {PROPOSAL_STATUSES}", name="ck_improvement_proposals_status_valid"
        ),
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    problem: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[str] = mapped_column(Text, nullable=False)
    historical_statistics: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    expected_benefit: Mapped[str] = mapped_column(Text, nullable=False)
    potential_risk: Mapped[str] = mapped_column(Text, nullable=False)
    implementation_difficulty: Mapped[str] = mapped_column(String(10), nullable=False)
    validation_results: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(10), default="pending", nullable=False, index=True)

    def __repr__(self) -> str:
        return f"ImprovementProposal(title={self.title!r}, status={self.status!r})"
