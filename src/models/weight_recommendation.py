"""ORM models for the AI Weight Optimizer (DATABASE.md: `weight_recommendations`,
`department_weight_overrides`).

Per the "AI Weight Optimizer" production requirement: "Create an optimizer
that does NOT automatically modify weights. Instead, analyze every 100
completed trades and generate a recommendation... User must explicitly
approve any weight changes." Every `WeightRecommendation` row starts
`status="pending"`; only an explicit user action moves it to
`approved`/`rejected`. `DepartmentWeightOverride` only ever gets a row
written when a recommendation is actually approved -- there is no code
path that writes to it automatically.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, CheckConstraint, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.database.postgres.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

WEIGHT_RECOMMENDATION_STATUSES: tuple[str, ...] = ("pending", "approved", "rejected")


class WeightRecommendation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One department's proposed weight adjustment for a completed 100-trade batch.

    Attributes:
        department_name: The department this recommendation is for, e.g.
            "technical", "correlation" (see
            `src.engines.learning_engine.factor_analysis.OPINION_DEPARTMENTS`).
        trade_batch_number: Which consecutive 100-trade batch this
            recommendation was generated for (1 = trades 1-100, 2 =
            trades 1-200, ...). Unique together with `department_name` so
            the optimizer never re-proposes the same batch twice.
        current_weight: The department's reliability score computed from
            every closed trade *before* this batch -- what has actually
            been driving live decisions up to now.
        suggested_weight: The department's reliability score computed
            from every closed trade *through* this batch -- what the
            newly-arrived evidence suggests instead.
        reason: A short, human-readable explanation of the direction and
            magnitude of the suggested change.
        supporting_stats: The measured statistics behind this suggestion
            (batch accuracy, batch sample size, correct/total calls) --
            never a fabricated justification.
        status: One of `WEIGHT_RECOMMENDATION_STATUSES`. Always starts "pending".
    """

    __tablename__ = "weight_recommendations"
    __table_args__ = (
        CheckConstraint(
            f"status IN {WEIGHT_RECOMMENDATION_STATUSES}",
            name="ck_weight_recommendations_status_valid",
        ),
    )

    department_name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    trade_batch_number: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    current_weight: Mapped[float] = mapped_column(Float, nullable=False)
    suggested_weight: Mapped[float] = mapped_column(Float, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    supporting_stats: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(10), default="pending", nullable=False, index=True)

    def __repr__(self) -> str:
        return (
            f"WeightRecommendation(department_name={self.department_name!r}, "
            f"status={self.status!r})"
        )


class DepartmentWeightOverride(Base, TimestampMixin):
    """A user-approved weight pinned for one department, overriding the
    live-computed reliability score until explicitly changed again.

    Attributes:
        department_name: Primary key -- one override per department.
        weight: The approved weight, taken verbatim from a
            `WeightRecommendation.suggested_weight` at approval time.
        source_recommendation_id: The `WeightRecommendation.id` this
            override was approved from, for audit traceability.
    """

    __tablename__ = "department_weight_overrides"

    department_name: Mapped[str] = mapped_column(String(50), primary_key=True)
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    source_recommendation_id: Mapped[str] = mapped_column(String(36), nullable=False)

    def __repr__(self) -> str:
        return f"DepartmentWeightOverride(department_name={self.department_name!r})"
