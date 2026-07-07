"""Integration tests for `BookChunkRepository`."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.book import Book, BookChunk
from src.repositories.book_chunk_repository import BookChunkRepository
from src.repositories.book_repository import BookRepository


async def _create_book(session: AsyncSession) -> Book:
    return await BookRepository(session).add(
        Book(title="Test Book", author="Author", source_path="test.pdf")
    )


async def test_list_by_book_orders_by_page(session: AsyncSession) -> None:
    book = await _create_book(session)
    repo = BookChunkRepository(session)
    await repo.add(BookChunk(book_id=book.id, page=2, text="second"))
    await repo.add(BookChunk(book_id=book.id, page=1, text="first"))

    chunks = await repo.list_by_book(book.id)

    assert [chunk.text for chunk in chunks] == ["first", "second"]


async def test_increment_usage_increases_count(session: AsyncSession) -> None:
    book = await _create_book(session)
    repo = BookChunkRepository(session)
    chunk = await repo.add(BookChunk(book_id=book.id, page=1, text="text"))
    assert chunk.usage_count == 0

    await repo.increment_usage(chunk.id)
    await repo.increment_usage(chunk.id)

    refreshed = await repo.get_by_id(chunk.id)
    assert refreshed is not None
    assert refreshed.usage_count == 2


async def test_increment_usage_is_noop_for_missing_chunk(session: AsyncSession) -> None:
    repo = BookChunkRepository(session)

    await repo.increment_usage(uuid.uuid4())  # must not raise
