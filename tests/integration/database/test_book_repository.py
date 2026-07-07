"""Integration tests for `BookRepository`."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.book import Book
from src.repositories.book_repository import BookRepository


async def test_add_and_get_by_source_path(session: AsyncSession) -> None:
    repo = BookRepository(session)
    await repo.add(
        Book(
            title="Reminiscences of a Stock Operator",
            author="Edwin Lefevre",
            source_path="books/uploaded/reminiscences.pdf",
        )
    )

    found = await repo.get_by_source_path("books/uploaded/reminiscences.pdf")

    assert found is not None
    assert found.title == "Reminiscences of a Stock Operator"


async def test_get_by_source_path_returns_none_when_missing(session: AsyncSession) -> None:
    repo = BookRepository(session)

    assert await repo.get_by_source_path("does/not/exist.pdf") is None


async def test_list_by_category(session: AsyncSession) -> None:
    repo = BookRepository(session)
    await repo.add(
        Book(title="A", author="X", source_path="a.pdf", category="smart_money")
    )
    await repo.add(Book(title="B", author="Y", source_path="b.pdf", category="risk"))

    results = await repo.list_by_category("smart_money")

    assert [book.title for book in results] == ["A"]


async def test_book_defaults_are_applied(session: AsyncSession) -> None:
    repo = BookRepository(session)
    book = await repo.add(Book(title="C", author="Z", source_path="c.pdf"))

    assert book.validation_status == "pending"
    assert book.quality_score == 0.0
