"""Domain repository for `BookClaim` entities."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.repositories.base import BaseRepository
from src.models.book_claim import BookClaim


class BookClaimRepository(BaseRepository[BookClaim]):
    """Repository for extracted book claims awaiting validation."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, BookClaim)

    async def list_pending(self, *, limit: int = 100) -> list[BookClaim]:
        """Fetch claims still awaiting historical validation.

        Per BOOK_RAG.md: "No claim becomes production knowledge
        automatically" — this is the validation queue the Historical
        Research Engine (a later roadmap phase) drains.

        Args:
            limit: Maximum number of claims to return.

        Returns:
            Matching `BookClaim` rows with `validation_status == "pending"`.
        """
        statement = (
            select(BookClaim).where(BookClaim.validation_status == "pending").limit(limit)
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())
