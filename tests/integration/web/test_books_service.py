"""Integration tests for the web UI's Books page data assembly."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.interfaces.web.books_service import get_books_page
from src.models.book import Book, BookChunk
from src.models.book_claim import BookClaim
from src.repositories.book_claim_repository import BookClaimRepository
from src.repositories.book_repository import BookRepository


async def _seed_book(session: AsyncSession, **overrides: object) -> Book:
    defaults: dict[str, object] = {
        "title": "Trading in the Zone",
        "author": "Mark Douglas",
        "source_path": "books/trading_in_the_zone.pdf",
    }
    defaults.update(overrides)
    return await BookRepository(session).add(Book(**defaults))


async def _seed_chunk(session: AsyncSession, book_id: object) -> BookChunk:
    chunk = BookChunk(book_id=book_id, text="Order blocks mark institutional entries.")
    session.add(chunk)
    await session.flush()
    return chunk


async def test_defaults_when_no_books_ingested_yet(session: AsyncSession) -> None:
    view = await get_books_page(session)

    assert view.processed == 0
    assert view.books == []
    assert view.claim_counts == {
        "pending": 0,
        "accepted": 0,
        "rejected": 0,
        "unknown": 0,
    }
    assert view.accepted_claims == []
    assert view.rejected_claims == []


async def test_lists_ingested_books(session: AsyncSession) -> None:
    await _seed_book(session, title="Reminiscences of a Stock Operator", category="psychology")
    await session.commit()

    view = await get_books_page(session)

    assert view.processed == 1
    assert view.books[0].title == "Reminiscences of a Stock Operator"
    assert view.books[0].category == "psychology"
    assert view.books[0].validation_status == "pending"


async def test_counts_and_samples_claims_by_status(session: AsyncSession) -> None:
    book = await _seed_book(session)
    chunk = await _seed_chunk(session, book.id)
    await BookClaimRepository(session).add(
        BookClaim(
            book_id=book.id,
            chunk_id=chunk.id,
            statement="Order Blocks increase probability",
            validation_status="accepted",
            confidence=0.8,
        )
    )
    await BookClaimRepository(session).add(
        BookClaim(
            book_id=book.id,
            chunk_id=chunk.id,
            statement="Astrology predicts gold moves",
            validation_status="rejected",
            confidence=0.1,
        )
    )
    await BookClaimRepository(session).add(
        BookClaim(
            book_id=book.id,
            chunk_id=chunk.id,
            statement="Not yet checked claim",
            validation_status="pending",
        )
    )
    await session.commit()

    view = await get_books_page(session)

    assert view.claim_counts == {"pending": 1, "accepted": 1, "rejected": 1, "unknown": 0}
    assert len(view.accepted_claims) == 1
    assert view.accepted_claims[0].statement == "Order Blocks increase probability"
    assert len(view.rejected_claims) == 1
    assert view.rejected_claims[0].statement == "Astrology predicts gold moves"
