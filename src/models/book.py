"""ORM models for the Book Engine (DATABASE.md: `books`, `book_chunks`).

Per BOOK_RAG.md: books are knowledge sources, never trading signals. Every
book and chunk carries provenance and quality metadata so downstream
consumers (RAG retrieval, Chief AI) can weigh evidence appropriately.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import JSON, CheckConstraint, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.postgres.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

VALIDATION_STATUSES: tuple[str, ...] = ("pending", "accepted", "rejected", "unknown")


class Book(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A single ingested book, paper or document (BOOK_RAG.md metadata).

    Attributes:
        title: Book title.
        author: Author name(s).
        edition: Edition string, e.g. "2nd Edition", if known.
        language: ISO 639-1 language code detected during ingestion.
        publisher: Publisher name, if known.
        category: Primary topic category (BOOK_RAG.md "Topic Classification").
        source_path: Filesystem path to the original uploaded document
            (`books/uploaded/`, per PROJECT_STRUCTURE.md).
        pages: Total page count.
        quality_score: Overall knowledge quality score in [0.0, 1.0]
            (BOOK_RAG.md "Book Scoring").
        validation_status: Whether the book's extracted claims have
            completed historical validation. Starts "pending".
    """

    __tablename__ = "books"
    __table_args__ = (
        CheckConstraint(
            f"validation_status IN {VALIDATION_STATUSES}", name="ck_books_validation_status"
        ),
    )

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    author: Mapped[str] = mapped_column(String(300), nullable=False)
    edition: Mapped[str | None] = mapped_column(String(50))
    language: Mapped[str | None] = mapped_column(String(10))
    publisher: Mapped[str | None] = mapped_column(String(300))
    category: Mapped[str | None] = mapped_column(String(100), index=True)
    source_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    pages: Mapped[int | None] = mapped_column(Integer)
    quality_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    validation_status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False, index=True
    )

    chunks: Mapped[list[BookChunk]] = relationship(
        back_populates="book", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"Book(title={self.title!r}, author={self.author!r})"


class BookChunk(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A single semantic chunk of a book, embedded and stored in Qdrant.

    The chunk's own `id` (a UUID) is used directly as the Qdrant point id
    for its embedding, so no separate "embedding id" column is needed
    (DATABASE.md lists one; here it is derived rather than duplicated).

    Attributes:
        book_id: Owning `Book`.
        page: Source page number, if known.
        chapter: Source chapter title, if known.
        section: Source section title, if known.
        text: The chunk's raw text content.
        topic: Primary predicted topic (BOOK_RAG.md "Topic Classification").
        entities: Extracted entities, keyed by category
            (BOOK_RAG.md "Entity Extraction").
        confidence: Confidence of the topic classification, in [0.0, 1.0].
        historical_validation: Validation status against historical data.
            Starts "pending" until the Historical Research Engine (a later
            roadmap phase) validates concepts extracted from this chunk.
        usage_count: Number of times this chunk was returned by RAG
            retrieval (BOOK_RAG.md "Learning: Was it referenced").
    """

    __tablename__ = "book_chunks"
    __table_args__ = (
        CheckConstraint(
            f"historical_validation IN {VALIDATION_STATUSES}",
            name="ck_book_chunks_historical_validation",
        ),
    )

    book_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True
    )
    page: Mapped[int | None] = mapped_column(Integer)
    chapter: Mapped[str | None] = mapped_column(String(300))
    section: Mapped[str | None] = mapped_column(String(300))
    text: Mapped[str] = mapped_column(Text, nullable=False)
    topic: Mapped[str | None] = mapped_column(String(100), index=True)
    entities: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    historical_validation: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False, index=True
    )
    usage_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    book: Mapped[Book] = relationship(back_populates="chunks")

    def __repr__(self) -> str:
        return f"BookChunk(book_id={self.book_id}, page={self.page}, topic={self.topic!r})"
