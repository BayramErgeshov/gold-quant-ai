"""Domain repository for `BookClaim` entities."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.repositories.base import BaseRepository
from src.models.book import VALIDATION_STATUSES
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
        statement = select(BookClaim).where(BookClaim.validation_status == "pending").limit(limit)
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def list_by_status(self, status: str, *, limit: int = 100) -> list[BookClaim]:
        """Fetch claims in a given validation status, most recently created first.

        Args:
            status: One of `src.models.book_claim.VALIDATION_STATUSES`.
            limit: Maximum number of claims to return.

        Returns:
            Matching `BookClaim` rows ordered by `created_at` descending.
        """
        statement = (
            select(BookClaim)
            .where(BookClaim.validation_status == status)
            .order_by(BookClaim.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def count_by_status(self) -> dict[str, int]:
        """Count claims grouped by validation status, without loading rows.

        Per the "Books" production requirement's UI: with tens of
        thousands of extracted claims, showing "validated hypotheses" and
        "rejected hypotheses" counts must not require fetching every row
        into memory just to count them.

        Returns:
            `{status: count}` for every status in `VALIDATION_STATUSES`,
            0 for any status with no rows -- never omitted, so the UI can
            always show a complete breakdown.
        """
        statement = select(BookClaim.validation_status, func.count()).group_by(
            BookClaim.validation_status
        )
        result = await self.session.execute(statement)
        counts: dict[str, int] = dict(result.tuples().all())
        return {status: counts.get(status, 0) for status in VALIDATION_STATUSES}
