"""Domain repository for `NewsArticle` entities."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.repositories.base import BaseRepository
from src.models.news_article import NewsArticle


class NewsArticleRepository(BaseRepository[NewsArticle]):
    """Repository for collected, deduplicated news articles."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, NewsArticle)

    async def get_by_content_hash(self, content_hash: str) -> NewsArticle | None:
        """Fetch an article by its deduplication hash.

        Args:
            content_hash: Hash of normalized title+source+published_at.

        Returns:
            The matching `NewsArticle`, or None if not yet stored
            (NEWS_ENGINE.md: "Never analyze the same news twice").
        """
        statement = select(NewsArticle).where(NewsArticle.content_hash == content_hash)
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def list_by_category(
        self, category: str, *, since: datetime | None = None, limit: int = 100
    ) -> list[NewsArticle]:
        """Fetch articles in a category, most recent first.

        Used for historical linking: finding prior articles in the same
        category as a newly ingested one (NEWS_ENGINE.md "Historical Reaction").

        Args:
            category: Classified event category, e.g. "central_bank".
            since: Only include articles published on or after this time.
            limit: Maximum number of articles to return.

        Returns:
            Matching `NewsArticle` rows ordered by `published_at` descending.
        """
        statement = (
            select(NewsArticle)
            .where(NewsArticle.category == category)
            .order_by(NewsArticle.published_at.desc())
            .limit(limit)
        )
        if since is not None:
            statement = statement.where(NewsArticle.published_at >= since)

        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def list_high_importance(
        self, *, min_importance: float = 0.7, limit: int = 100
    ) -> list[NewsArticle]:
        """Fetch high-importance articles, most recent first.

        Per the "Market Replay Mode" production requirement: "Allow
        replay of Major News Events (CPI/NFP/FOMC)" -- this surfaces
        candidate dates for the user to pick a replay window around,
        using this platform's own already-computed importance score
        rather than a hardcoded event list.

        Args:
            min_importance: Minimum `importance_score` to include.
            limit: Maximum number of articles to return.

        Returns:
            Matching `NewsArticle` rows ordered by `published_at` descending.
        """
        statement = (
            select(NewsArticle)
            .where(NewsArticle.importance_score >= min_importance)
            .order_by(NewsArticle.published_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())
