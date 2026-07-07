"""Integration tests for news historical linking."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from src.engines.news_engine.linking import find_related_articles
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
    return NewsArticle(**defaults)  # type: ignore[arg-type]


async def test_finds_prior_articles_in_same_category(session: AsyncSession) -> None:
    repository = NewsArticleRepository(session)
    older = await repository.add(
        _article(content_hash="h1", category="central_bank", title="Older")
    )
    newest = await repository.add(
        _article(
            content_hash="h2",
            category="central_bank",
            title="Newest",
            published_at=_PUBLISHED_AT + timedelta(days=1),
        )
    )
    await repository.add(_article(content_hash="h3", category="inflation", title="Unrelated"))

    related = await find_related_articles(repository, newest)

    assert [article.id for article in related] == [older.id]


async def test_excludes_the_article_itself(session: AsyncSession) -> None:
    repository = NewsArticleRepository(session)
    older = await repository.add(
        _article(content_hash="h1", category="central_bank", title="Older")
    )
    article = await repository.add(
        _article(
            content_hash="h2",
            category="central_bank",
            title="Self",
            published_at=_PUBLISHED_AT + timedelta(days=1),
        )
    )

    related = await find_related_articles(repository, article)

    assert article.id not in [candidate.id for candidate in related]
    assert older.id in [candidate.id for candidate in related]


async def test_returns_empty_for_unclassified_article(session: AsyncSession) -> None:
    repository = NewsArticleRepository(session)
    article = await repository.add(_article(content_hash="h1", category=None))

    related = await find_related_articles(repository, article)

    assert related == []


async def test_respects_limit(session: AsyncSession) -> None:
    repository = NewsArticleRepository(session)
    for index in range(3):
        await repository.add(
            _article(
                content_hash=f"h{index}",
                category="central_bank",
                published_at=_PUBLISHED_AT + timedelta(days=index),
            )
        )
    newest = await repository.add(
        _article(
            content_hash="h-newest",
            category="central_bank",
            published_at=_PUBLISHED_AT + timedelta(days=10),
        )
    )

    related = await find_related_articles(repository, newest, limit=2)

    assert len(related) == 2
