"""ORM model for extracted claims awaiting validation (BOOK_RAG.md: "Claim Extraction").

Per BOOK_RAG.md: "Every important statement becomes a claim... No claim
becomes production knowledge automatically." Claims start `pending` and
are only ever moved to `accepted`/`rejected` by the Historical Research
Engine's statistical validation (a later roadmap phase) — never by the
Book Engine itself.
"""

from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.database.postgres.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from src.models.book import VALIDATION_STATUSES


class BookClaim(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A single extracted, checkable claim from a book chunk.

    Attributes:
        book_id: Owning `Book`.
        chunk_id: Source `BookChunk` the claim was extracted from.
        statement: The claim text, e.g. "Order Blocks increase probability".
        topic: Topic category the claim belongs to.
        validation_status: pending/accepted/rejected/unknown.
        confidence: Confidence once validated; 0.0 while `pending`.
    """

    __tablename__ = "book_claims"
    __table_args__ = (
        CheckConstraint(
            f"validation_status IN {VALIDATION_STATUSES}", name="ck_book_claims_validation_status"
        ),
    )

    book_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("book_chunks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    topic: Mapped[str | None] = mapped_column(String(100), index=True)
    validation_status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False, index=True
    )
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    def __repr__(self) -> str:
        return f"BookClaim(topic={self.topic!r}, status={self.validation_status!r})"
