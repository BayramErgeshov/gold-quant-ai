"""Approve/reject handling for the AI Weight Optimizer's recommendations.

Per the "AI Weight Optimizer" production requirement: "User must
explicitly approve any weight changes." Approving here is the *only*
code path that ever writes a `DepartmentWeightOverride` -- rejecting
just records the decision, matching how `ImprovementProposal` review
works (SELF_LEARNING_ENGINE.md "User Approval").
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.weight_recommendation import WeightRecommendation
from src.repositories.weight_recommendation_repository import (
    DepartmentWeightOverrideRepository,
    WeightRecommendationRepository,
)


@dataclass(frozen=True, slots=True)
class WeightRecommendationView:
    """A serializable, read-only projection of one `WeightRecommendation`.

    FastAPI/Pydantic cannot build a response model directly from a
    SQLAlchemy ORM instance, so every route returns this plain dataclass
    instead of the ORM row itself.
    """

    id: str
    department_name: str
    trade_batch_number: int
    current_weight: float
    suggested_weight: float
    reason: str
    supporting_stats: dict[str, Any]
    status: str
    created_at: datetime


def to_view(recommendation: WeightRecommendation) -> WeightRecommendationView:
    return WeightRecommendationView(
        id=str(recommendation.id),
        department_name=recommendation.department_name,
        trade_batch_number=recommendation.trade_batch_number,
        current_weight=recommendation.current_weight,
        suggested_weight=recommendation.suggested_weight,
        reason=recommendation.reason,
        supporting_stats=recommendation.supporting_stats,
        status=recommendation.status,
        created_at=recommendation.created_at,
    )


@dataclass(frozen=True, slots=True)
class WeightRecommendationsView:
    """Every weight recommendation the user might want to review.

    Attributes:
        pending: Recommendations awaiting a decision, oldest first.
        recent: Every recommendation (any status), most recent first.
    """

    pending: list[WeightRecommendationView] = field(default_factory=list)
    recent: list[WeightRecommendationView] = field(default_factory=list)


async def get_weight_recommendations(session: AsyncSession) -> WeightRecommendationsView:
    """Assemble the current Weight Optimizer view.

    Args:
        session: The active database session.

    Returns:
        A `WeightRecommendationsView` computed entirely from persisted rows.
    """
    repository = WeightRecommendationRepository(session)
    return WeightRecommendationsView(
        pending=[to_view(row) for row in await repository.list_pending()],
        recent=[to_view(row) for row in await repository.list_recent()],
    )


class WeightRecommendationNotFoundError(Exception):
    """Raised when a recommendation id does not exist."""


class WeightRecommendationAlreadyDecidedError(Exception):
    """Raised when trying to decide a recommendation that isn't pending."""


async def _get_pending_recommendation(
    session: AsyncSession, recommendation_id: str
) -> WeightRecommendation:
    try:
        parsed_id = uuid.UUID(recommendation_id)
    except ValueError as error:
        raise WeightRecommendationNotFoundError(recommendation_id) from error

    repository = WeightRecommendationRepository(session)
    recommendation = await repository.get_by_id(parsed_id)
    if recommendation is None:
        raise WeightRecommendationNotFoundError(recommendation_id)
    if recommendation.status != "pending":
        raise WeightRecommendationAlreadyDecidedError(recommendation_id)
    return recommendation


async def approve_weight_recommendation(
    session: AsyncSession, recommendation_id: str
) -> WeightRecommendation:
    """Approve a pending recommendation, pinning its suggested weight.

    Args:
        session: The active database session.
        recommendation_id: The `WeightRecommendation.id` to approve.

    Returns:
        The updated `WeightRecommendation`, now `status == "approved"`.

    Raises:
        WeightRecommendationNotFoundError: If no such recommendation exists.
        WeightRecommendationAlreadyDecidedError: If it was already approved/rejected.
    """
    recommendation = await _get_pending_recommendation(session, recommendation_id)
    recommendation.status = "approved"
    repository = WeightRecommendationRepository(session)
    await repository.add(recommendation)

    await DepartmentWeightOverrideRepository(session).upsert(
        recommendation.department_name,
        recommendation.suggested_weight,
        source_recommendation_id=str(recommendation.id),
    )
    return recommendation


async def reject_weight_recommendation(
    session: AsyncSession, recommendation_id: str
) -> WeightRecommendation:
    """Reject a pending recommendation -- the live weight is left untouched.

    Args:
        session: The active database session.
        recommendation_id: The `WeightRecommendation.id` to reject.

    Returns:
        The updated `WeightRecommendation`, now `status == "rejected"`.

    Raises:
        WeightRecommendationNotFoundError: If no such recommendation exists.
        WeightRecommendationAlreadyDecidedError: If it was already approved/rejected.
    """
    recommendation = await _get_pending_recommendation(session, recommendation_id)
    recommendation.status = "rejected"
    repository = WeightRecommendationRepository(session)
    await repository.add(recommendation)
    return recommendation
