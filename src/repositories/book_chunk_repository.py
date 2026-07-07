"""Domain repository for `BookChunk` entities."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.repositories.base import BaseRepository
from src.models.book import BookChunk


class BookChunkRepository(BaseRepository[BookChunk]):
    """Repository for book chunks."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, BookChunk)

    async def list_by_book(self, book_id: uuid.UUID) -> list[BookChunk]:
        """Fetch every chunk belonging to a book, in page order.

        Args:
            book_id: Owning book's id.

        Returns:
            Matching `BookChunk` rows ordered by page.
        """
        statement = (
            select(BookChunk).where(BookChunk.book_id == book_id).order_by(BookChunk.page)
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def increment_usage(self, chunk_id: uuid.UUID) -> None:
        """Record that a chunk was returned by RAG retrieval.

        Args:
            chunk_id: The retrieved chunk's id.
        """
        chunk = await self.get_by_id(chunk_id)
        if chunk is not None:
            chunk.usage_count += 1
            await self.session.flush()
