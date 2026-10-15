"""Domain repository for `ImprovementProposal` entities."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.repositories.base import BaseRepository
from src.models.improvement_proposal import ImprovementProposal


class ImprovementProposalRepository(BaseRepository[ImprovementProposal]):
    """Repository for user-reviewable improvement proposals."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, ImprovementProposal)

    async def list_pending(self, *, limit: int = 100) -> list[ImprovementProposal]:
        """Fetch every proposal awaiting user review, oldest first.

        Args:
            limit: Maximum number of proposals to return.

        Returns:
            `ImprovementProposal` rows with `status == "pending"`, ordered
            by `created_at` ascending (SELF_LEARNING_ENGINE.md "User
            Approval": nothing here auto-approves; the oldest pending
            request surfaces first).
        """
        statement = (
            select(ImprovementProposal)
            .where(ImprovementProposal.status == "pending")
            .order_by(ImprovementProposal.created_at)
            .limit(limit)
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def exists_with_title(self, title: str) -> bool:
        """Check whether a proposal with this exact title already exists.

        Used to avoid raising the same hypothesis as a duplicate pending
        proposal every time a new losing trade re-triggers the recurring-
        factor scan (SELF_LEARNING_ENGINE.md "User Approval": a proposal
        awaits a single explicit decision, not repeated re-submission).

        Args:
            title: The candidate proposal's title (built from a
                `Hypothesis.question`, deterministic for a given
                recurring factor name).

        Returns:
            True if any proposal (pending, approved, or rejected) already
            has this title.
        """
        statement = select(ImprovementProposal.id).where(ImprovementProposal.title == title)
        result = await self.session.execute(statement)
        return result.scalar_one_or_none() is not None
