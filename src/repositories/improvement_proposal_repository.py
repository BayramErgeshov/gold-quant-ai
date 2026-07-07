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
