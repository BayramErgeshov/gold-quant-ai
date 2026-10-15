"""Domain repository for `BookChunk` entities."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.repositories.base import BaseRepository
from src.models.book import BookChunk


class BookChunkRepository(BaseRepository[BookChunk]):
    """Repository for book chunks."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, BookChunk)

    async def list_by_book(
        self, book_id: uuid.UUID, *, limit: int | None = None
    ) -> list[BookChunk]:
        """Fetch chunks belonging to a book, in page order.

        Args:
            book_id: Owning book's id.
            limit: Maximum number of chunks to return, oldest page first.
                None (the default) returns every chunk — an institutional
                audit finding: a book with an unusually large number of
                chunks could otherwise load all of them into memory at
                once; callers with a very large book should pass an
                explicit limit.

        Returns:
            Matching `BookChunk` rows ordered by page.
        """
        statement = select(BookChunk).where(BookChunk.book_id == book_id).order_by(BookChunk.page)
        if limit is not None:
            statement = statement.limit(limit)
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def count_by_topic(self) -> dict[str, int]:
        """Count how many chunks the knowledge base has per classified topic.

        Used by `src.engines.book_engine.book_suggestions` to identify
        topics the current book library covers thinly — never counts a
        topic no chunk actually has (chunks with `topic=None` are excluded).

        Returns:
            `{topic: chunk_count}` for every topic with at least one chunk.
        """
        statement = (
            select(BookChunk.topic, func.count(BookChunk.id))
            .where(BookChunk.topic.is_not(None))
            .group_by(BookChunk.topic)
        )
        result = await self.session.execute(statement)
        return {topic: count for topic, count in result.all() if topic is not None}

    async def increment_usage(self, chunk_id: uuid.UUID) -> None:
        """Record that a chunk was returned by RAG retrieval.

        Args:
            chunk_id: The retrieved chunk's id.
        """
        chunk = await self.get_by_id(chunk_id)
        if chunk is not None:
            chunk.usage_count += 1
            await self.session.flush()
