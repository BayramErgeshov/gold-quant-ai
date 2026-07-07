"""Integration tests for `BookClaimRepository`."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.book import Book, BookChunk
from src.models.book_claim import BookClaim
from src.repositories.book_chunk_repository import BookChunkRepository
from src.repositories.book_claim_repository import BookClaimRepository
from src.repositories.book_repository import BookRepository


async def test_list_pending_excludes_validated_claims(session: AsyncSession) -> None:
    book = await BookRepository(session).add(
        Book(title="Book", author="Author", source_path="book.pdf")
    )
    chunk = await BookChunkRepository(session).add(
        BookChunk(book_id=book.id, page=1, text="text")
    )
    repo = BookClaimRepository(session)
    await repo.add(
        BookClaim(book_id=book.id, chunk_id=chunk.id, statement="Pending claim", topic="risk")
    )
    await repo.add(
        BookClaim(
            book_id=book.id,
            chunk_id=chunk.id,
            statement="Accepted claim",
            topic="risk",
            validation_status="accepted",
        )
    )

    pending = await repo.list_pending()

    assert [claim.statement for claim in pending] == ["Pending claim"]
