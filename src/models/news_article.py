"""ORM model for collected news articles (DATABASE.md: `news_events`).

Per NEWS_ENGINE.md: "Every news item must be Collected, Verified,
Deduplicated, Classified, Ranked, Linked to historical events... Assigned
an expected impact, Stored for future learning." `content_hash` enforces
deduplication at the database level (NEWS_ENGINE.md: "Never analyze the
same news twice").
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, CheckConstraint, DateTime, Float, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.database.postgres.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

EXPECTED_VOLATILITY_LEVELS: tuple[str, ...] = ("low", "medium", "high")


class NewsArticle(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A single deduplicated, classified news article.

    Attributes:
        title: Article headline.
        summary: Short summary/excerpt, if available.
        source: Publisher name, e.g. "reuters.com".
        url: Original article URL, if available.
        published_at: When the article was published (source-reported, UTC).
        category: Classified event category (NEWS_ENGINE.md "Event Types"),
            e.g. "central_bank", "inflation".
        entities: Extracted entities, keyed by category (reuses
            `src.engines.book_engine.entity_extraction`).
        importance_score: Combined importance score in [0.0, 1.0]
            (NEWS_ENGINE.md "Importance Score").
        expected_volatility: One of `EXPECTED_VOLATILITY_LEVELS`.
        content_hash: Hash of normalized title+source+published_at, used
            to reject duplicate articles at the database level.
    """

    __tablename__ = "news_articles"
    __table_args__ = (
        UniqueConstraint("content_hash", name="uq_news_articles_content_hash"),
        CheckConstraint(
            f"expected_volatility IN {EXPECTED_VOLATILITY_LEVELS}",
            name="ck_news_articles_expected_volatility",
        ),
    )

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    url: Mapped[str | None] = mapped_column(String(1000))
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    category: Mapped[str | None] = mapped_column(String(100), index=True)
    entities: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    importance_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    expected_volatility: Mapped[str] = mapped_column(String(10), default="low", nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    def __repr__(self) -> str:
        return f"NewsArticle(title={self.title!r}, source={self.source!r})"
