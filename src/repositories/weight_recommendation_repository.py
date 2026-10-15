"""Domain repositories for the AI Weight Optimizer."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.repositories.base import BaseRepository
from src.models.weight_recommendation import DepartmentWeightOverride, WeightRecommendation


class WeightRecommendationRepository(BaseRepository[WeightRecommendation]):
    """Repository for user-reviewable weight-change recommendations."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, WeightRecommendation)

    async def exists_for_batch(self, department_name: str, trade_batch_number: int) -> bool:
        """Check whether this department already has a recommendation for this batch.

        Used by the optimizer to avoid re-proposing the same 100-trade
        batch twice if the live loop's cheap per-cycle check runs again
        before the batch number advances.

        Args:
            department_name: The department to check.
            trade_batch_number: The consecutive 100-trade batch number.

        Returns:
            True if a recommendation already exists for this department/batch pair.
        """
        statement = select(WeightRecommendation.id).where(
            WeightRecommendation.department_name == department_name,
            WeightRecommendation.trade_batch_number == trade_batch_number,
        )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none() is not None

    async def list_pending(self, *, limit: int = 100) -> list[WeightRecommendation]:
        """Fetch every recommendation awaiting user review, oldest first.

        Args:
            limit: Maximum number of recommendations to return.

        Returns:
            `WeightRecommendation` rows with `status == "pending"`,
            ordered by `created_at` ascending -- nothing here auto-approves.
        """
        statement = (
            select(WeightRecommendation)
            .where(WeightRecommendation.status == "pending")
            .order_by(WeightRecommendation.created_at)
            .limit(limit)
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def list_recent(self, *, limit: int = 200) -> list[WeightRecommendation]:
        """Fetch every recommendation, most recent first.

        Args:
            limit: Maximum number of recommendations to return.

        Returns:
            `WeightRecommendation` rows ordered by `created_at` descending.
        """
        statement = (
            select(WeightRecommendation)
            .order_by(WeightRecommendation.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())


class DepartmentWeightOverrideRepository:
    """Repository for user-approved department weight overrides.

    Not a `BaseRepository` subclass: `DepartmentWeightOverride` is keyed
    by `department_name`, not a UUID `id`, so the generic `get_by_id`
    contract does not apply.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_all(self) -> dict[str, float]:
        """Fetch every approved override.

        Returns:
            `{department_name: weight}` for every department with an
            approved override. A department absent here has no override
            -- callers should fall back to the live-computed reliability
            score, never assume a neutral weight silently.
        """
        statement = select(DepartmentWeightOverride)
        result = await self.session.execute(statement)
        return {row.department_name: row.weight for row in result.scalars().all()}

    async def upsert(
        self, department_name: str, weight: float, *, source_recommendation_id: str
    ) -> DepartmentWeightOverride:
        """Set (or replace) the approved override for one department.

        Args:
            department_name: The department to override.
            weight: The approved weight.
            source_recommendation_id: The `WeightRecommendation.id` this
                override was approved from.

        Returns:
            The persisted `DepartmentWeightOverride`.
        """
        existing = await self.session.get(DepartmentWeightOverride, department_name)
        if existing is not None:
            existing.weight = weight
            existing.source_recommendation_id = source_recommendation_id
            await self.session.flush()
            await self.session.refresh(existing)
            return existing

        override = DepartmentWeightOverride(
            department_name=department_name,
            weight=weight,
            source_recommendation_id=source_recommendation_id,
        )
        self.session.add(override)
        await self.session.flush()
        await self.session.refresh(override)
        return override
