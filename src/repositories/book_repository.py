"""Domain repository for `Book` entities."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.repositories.base import BaseRepository
from src.models.book import Book


class BookRepository(BaseRepository[Book]):
    """Repository for ingested books."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Book)

    async def get_by_source_path(self, source_path: str) -> Book | None:
        """Fetch a book by its source file path, used to detect re-ingestion.

        Args:
            source_path: Filesystem path the book was ingested from.

        Returns:
            The matching `Book`, or None if it has not been ingested yet.
        """
        statement = select(Book).where(Book.source_path == source_path)
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def list_by_category(self, category: str) -> list[Book]:
        """Fetch every book belonging to a topic category.

        Args:
            category: Topic category, e.g. "smart_money".

        Returns:
            Matching `Book` rows.
        """
        statement = select(Book).where(Book.category == category)
        result = await self.session.execute(statement)
        return list(result.scalars().all())
