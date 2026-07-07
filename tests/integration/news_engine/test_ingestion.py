"""Integration tests for `NewsIngestionService`."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.data_collection.exceptions import AllProvidersFailedError
from src.core.data_collection.fallback import FallbackChain
from src.core.data_collection.models import ProviderTier, SourceCategory
from src.core.data_collection.provider import DataProvider
from src.engines.news_engine.ingestion import NewsIngestionService
from src.repositories.news_article_repository import NewsArticleRepository


@pytest.fixture(autouse=True)
def _no_real_redis() -> None:
    # This suite tests ingestion logic on top of a working FallbackChain,
    # not the Redis-backed cache itself (already covered in
    # tests/unit/core/data_collection/test_cache.py and test_fallback.py).
    with (
        patch("src.core.data_collection.fallback.set_cached", AsyncMock()),
        patch("src.core.data_collection.fallback.get_cached", AsyncMock(return_value=None)),
    ):
        yield


_SAMPLE_ARTICLES = [
    {
        "source": {"id": "reuters", "name": "Reuters"},
        "title": "Federal Reserve holds interest rates steady",
        "description": "The FOMC decision affects USD and gold markets.",
        "url": "https://reuters.com/fed-holds-rates",
        "publishedAt": "2026-01-01T09:00:00Z",
    },
    {
        "source": {"id": None, "name": "Bloomberg"},
        "title": "Gold prices rise on inflation data",
        "description": "US CPI rose more than expected.",
        "url": "https://bloomberg.com/gold-inflation",
        "publishedAt": "2026-01-01T10:00:00Z",
    },
]


class _FakeNewsProvider(DataProvider[list[dict[str, object]]]):
    name = "fake_news_provider"
    category = SourceCategory.NEWS
    tier = ProviderTier.TIER_2
    reliability = 0.75

    def __init__(
        self,
        *,
        configured: bool = True,
        articles: list[dict[str, object]] | None = None,
    ) -> None:
        self._configured = configured
        self._articles = articles if articles is not None else _SAMPLE_ARTICLES

    @property
    def is_configured(self) -> bool:
        return self._configured

    async def fetch(self, **kwargs: object) -> list[dict[str, object]]:
        return self._articles


async def test_ingest_stores_classified_articles(session: AsyncSession) -> None:
    chain: FallbackChain[list[dict[str, object]]] = FallbackChain(
        [_FakeNewsProvider()], category=SourceCategory.NEWS
    )
    repository = NewsArticleRepository(session)
    service = NewsIngestionService(article_repository=repository, fallback_chain=chain)

    result = await service.ingest("gold OR XAUUSD")

    assert result.requested == 2
    assert result.inserted == 2
    assert result.skipped_duplicates == 0
    assert result.skipped_incomplete == 0

    stored = await repository.list_all(limit=10)
    assert len(stored) == 2
    fed_article = next(article for article in stored if "Federal Reserve" in article.title)
    assert fed_article.category == "central_bank"
    assert fed_article.expected_volatility == "high"
    assert fed_article.source == "Reuters"


async def test_ingest_is_idempotent_on_repeated_calls(session: AsyncSession) -> None:
    chain: FallbackChain[list[dict[str, object]]] = FallbackChain(
        [_FakeNewsProvider()], category=SourceCategory.NEWS
    )
    repository = NewsArticleRepository(session)
    service = NewsIngestionService(article_repository=repository, fallback_chain=chain)

    await service.ingest("gold OR XAUUSD")
    second_result = await service.ingest("gold OR XAUUSD")

    assert second_result.inserted == 0
    assert second_result.skipped_duplicates == 2
    stored = await repository.list_all(limit=10)
    assert len(stored) == 2


async def test_ingest_skips_incomplete_articles(session: AsyncSession) -> None:
    published_at = "2026-01-01T09:00:00Z"
    incomplete_articles: list[dict[str, object]] = [
        {"source": {"name": "Reuters"}, "title": None, "publishedAt": published_at},
        {"source": {"name": None}, "title": "Missing source", "publishedAt": published_at},
        {"source": {"name": "Reuters"}, "title": "Missing date", "publishedAt": None},
    ]
    chain: FallbackChain[list[dict[str, object]]] = FallbackChain(
        [_FakeNewsProvider(articles=incomplete_articles)], category=SourceCategory.NEWS
    )
    repository = NewsArticleRepository(session)
    service = NewsIngestionService(article_repository=repository, fallback_chain=chain)

    result = await service.ingest("gold OR XAUUSD")

    assert result.requested == 3
    assert result.inserted == 0
    assert result.skipped_incomplete == 3


async def test_ingest_propagates_failure_when_no_provider_configured(
    session: AsyncSession,
) -> None:
    chain: FallbackChain[list[dict[str, object]]] = FallbackChain(
        [_FakeNewsProvider(configured=False)], category=SourceCategory.NEWS
    )
    repository = NewsArticleRepository(session)
    service = NewsIngestionService(article_repository=repository, fallback_chain=chain)

    with pytest.raises(AllProvidersFailedError):
        await service.ingest("gold OR XAUUSD")
