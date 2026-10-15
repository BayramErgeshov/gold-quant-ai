"""Integration tests for the AI Weight Optimizer's approve/reject service."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.interfaces.web.weight_recommendation_service import (
    WeightRecommendationAlreadyDecidedError,
    WeightRecommendationNotFoundError,
    approve_weight_recommendation,
    get_weight_recommendations,
    reject_weight_recommendation,
)
from src.models.weight_recommendation import WeightRecommendation
from src.repositories.weight_recommendation_repository import (
    DepartmentWeightOverrideRepository,
    WeightRecommendationRepository,
)


def _draft_recommendation(**overrides: object) -> WeightRecommendation:
    defaults: dict[str, object] = {
        "department_name": "technical",
        "trade_batch_number": 1,
        "current_weight": 1.0,
        "suggested_weight": 0.7,
        "reason": "Lower predictive accuracy for technical during the last 100 trades.",
        "supporting_stats": {
            "batch_accuracy": 0.7,
            "batch_total_calls": 40,
            "batch_correct_calls": 28,
        },
    }
    defaults.update(overrides)
    return WeightRecommendation(**defaults)


async def test_get_weight_recommendations_lists_pending_and_recent(session: AsyncSession) -> None:
    await WeightRecommendationRepository(session).add(_draft_recommendation())

    view = await get_weight_recommendations(session)

    assert len(view.pending) == 1
    assert len(view.recent) == 1


async def test_approve_pins_the_suggested_weight_as_an_override(session: AsyncSession) -> None:
    recommendation = await WeightRecommendationRepository(session).add(_draft_recommendation())

    approved = await approve_weight_recommendation(session, str(recommendation.id))

    assert approved.status == "approved"
    overrides = await DepartmentWeightOverrideRepository(session).get_all()
    assert overrides["technical"] == pytest.approx(0.7)


async def test_reject_does_not_write_an_override(session: AsyncSession) -> None:
    recommendation = await WeightRecommendationRepository(session).add(_draft_recommendation())

    rejected = await reject_weight_recommendation(session, str(recommendation.id))

    assert rejected.status == "rejected"
    overrides = await DepartmentWeightOverrideRepository(session).get_all()
    assert overrides == {}


async def test_approve_raises_for_an_unknown_id(session: AsyncSession) -> None:
    with pytest.raises(WeightRecommendationNotFoundError):
        await approve_weight_recommendation(session, str(uuid.uuid4()))


async def test_approve_raises_for_a_malformed_id(session: AsyncSession) -> None:
    with pytest.raises(WeightRecommendationNotFoundError):
        await approve_weight_recommendation(session, "not-a-uuid")


async def test_approve_twice_raises_already_decided(session: AsyncSession) -> None:
    recommendation = await WeightRecommendationRepository(session).add(_draft_recommendation())
    await approve_weight_recommendation(session, str(recommendation.id))

    with pytest.raises(WeightRecommendationAlreadyDecidedError):
        await approve_weight_recommendation(session, str(recommendation.id))
