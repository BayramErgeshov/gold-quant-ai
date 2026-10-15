"""Integration tests for `NewsArticleRepository`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.news_article import NewsArticle
from src.repositories.news_article_repository import NewsArticleRepository

_PUBLISHED_AT = datetime(2026, 1, 1, tzinfo=UTC)


def _article(**overrides: object) -> NewsArticle:
    defaults: dict[str, object] = {
        "title": "Fed holds rates steady",
        "source": "reuters.com",
        "published_at": _PUBLISHED_AT,
        "content_hash": "hash-1",
    }
    defaults.update(overrides)
    return NewsArticle(**defaults)


async def test_get_by_content_hash_finds_existing_article(session: AsyncSession) -> None:
    repo = NewsArticleRepository(session)
    await repo.add(_article(content_hash="unique-hash"))

    found = await repo.get_by_content_hash("unique-hash")

    assert found is not None
    assert found.title == "Fed holds rates steady"


async def test_get_by_content_hash_returns_none_when_missing(session: AsyncSession) -> None:
    repo = NewsArticleRepository(session)

    assert await repo.get_by_content_hash("does-not-exist") is None


async def test_list_by_category_orders_most_recent_first(session: AsyncSession) -> None:
    repo = NewsArticleRepository(session)
    await repo.add(
        _article(
            content_hash="h1",
            category="central_bank",
            title="Older",
            published_at=_PUBLISHED_AT,
        )
    )
    await repo.add(
        _article(
            content_hash="h2",
            category="central_bank",
            title="Newer",
            published_at=_PUBLISHED_AT + timedelta(days=1),
        )
    )
    await repo.add(_article(content_hash="h3", category="inflation", title="Unrelated category"))

    results = await repo.list_by_category("central_bank")

    assert [article.title for article in results] == ["Newer", "Older"]


async def test_list_by_category_filters_by_since(session: AsyncSession) -> None:
    repo = NewsArticleRepository(session)
    await repo.add(
        _article(
            content_hash="h1",
            category="central_bank",
            published_at=_PUBLISHED_AT,
        )
    )
    await repo.add(
        _article(
            content_hash="h2",
            category="central_bank",
            published_at=_PUBLISHED_AT + timedelta(days=10),
        )
    )

    results = await repo.list_by_category("central_bank", since=_PUBLISHED_AT + timedelta(days=5))

    assert len(results) == 1


async def test_list_high_importance_filters_below_threshold(session: AsyncSession) -> None:
    repo = NewsArticleRepository(session)
    await repo.add(_article(content_hash="h1", importance_score=0.9, title="High impact"))
    await repo.add(_article(content_hash="h2", importance_score=0.3, title="Low impact"))

    results = await repo.list_high_importance(min_importance=0.7)

    assert [article.title for article in results] == ["High impact"]
