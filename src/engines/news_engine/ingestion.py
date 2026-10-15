"""NewsAPI news ingestion pipeline.

Fetches articles matching a query from NewsAPI (Phase 3's `NewsApiProvider`,
via the standard `FallbackChain`), processes them (classification, entity
extraction, importance/volatility scoring) and stores newly seen articles,
skipping ones already stored by content hash (NEWS_ENGINE.md "Never analyze
the same news twice"). Activates automatically once `NEWSAPI_API_KEY` is
added to `.env`; adding a higher-tier provider (e.g. a direct Reuters/
Bloomberg feed) later is a matter of extending the `FallbackChain`'s
provider list, per DATA_COLLECTION_ENGINE.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.common.logging import get_logger
from src.core.data_collection.cache import build_cache_key
from src.core.data_collection.fallback import FallbackChain
from src.core.data_collection.models import SourceCategory
from src.engines.news_engine.cleaning import clean_article_text
from src.engines.news_engine.processing import process_raw_article
from src.models.news_article import NewsArticle
from src.repositories.news_article_repository import NewsArticleRepository
from src.services.news.providers.newsapi_provider import (
    REPUTABLE_FINANCIAL_DOMAINS,
    NewsApiProvider,
)
from src.settings import Settings, get_settings

logger = get_logger(__name__)

_DATA_CATEGORY = SourceCategory.NEWS


@dataclass(frozen=True, slots=True)
class NewsIngestionResult:
    """Outcome of a single news ingestion run.

    Attributes:
        requested: Number of articles returned by the provider/cache.
        skipped_duplicates: Number already stored (matched by content hash).
        skipped_incomplete: Number missing a title, source or publish date.
        inserted: Number of newly stored articles.
    """

    requested: int
    skipped_duplicates: int
    skipped_incomplete: int
    inserted: int


def _parse_published_at(raw: str) -> datetime:
    """Parse a NewsAPI ISO-8601 timestamp, e.g. "2024-01-01T00:00:00Z"."""
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


class NewsIngestionService:
    """Fetches, classifies, scores and stores news articles for a query."""

    def __init__(
        self,
        *,
        article_repository: NewsArticleRepository,
        settings: Settings | None = None,
        fallback_chain: FallbackChain[list[dict[str, Any]]] | None = None,
    ) -> None:
        """Initialize the service.

        Args:
            article_repository: Persists deduplicated, scored articles.
            settings: Application settings. Defaults to `get_settings()`.
            fallback_chain: Provider chain to fetch articles from. Defaults
                to a chain containing only `NewsApiProvider`; injectable
                for testing and for adding higher-tier providers later.
        """
        resolved_settings = settings or get_settings()
        self._articles = article_repository
        self._fallback_chain = fallback_chain or FallbackChain(
            [NewsApiProvider(resolved_settings)], category=_DATA_CATEGORY
        )

    async def ingest(
        self,
        query: str,
        *,
        page_size: int = 20,
        domains: tuple[str, ...] = REPUTABLE_FINANCIAL_DOMAINS,
    ) -> NewsIngestionResult:
        """Fetch, classify and store news articles matching a query.

        Args:
            query: Search query, e.g. "gold OR XAUUSD".
            page_size: Maximum number of articles to request.
            domains: Restrict results to these publisher domains (NewsAPI's
                own `domains` filter). Defaults to
                `REPUTABLE_FINANCIAL_DOMAINS` (Reuters, Bloomberg, FT,
                WSJ, CNBC, MarketWatch) -- per the "News Intelligence"
                production requirement's source-quality bar. Pass an
                empty tuple to search every source NewsAPI aggregates.

        Returns:
            A `NewsIngestionResult` summarizing what was fetched and stored.

        Raises:
            src.core.data_collection.exceptions.AllProvidersFailedError:
                If no provider is configured/reachable and nothing is
                cached (e.g. `NEWSAPI_API_KEY` is not set yet) — never
                fabricated as empty/fake data.
        """
        domains_param = ",".join(domains)
        cache_key = build_cache_key(
            _DATA_CATEGORY.value, f"newsapi:{query}:{page_size}:{domains_param}"
        )
        dataset = await self._fallback_chain.fetch(
            cache_key, query=query, page_size=page_size, domains=domains_param
        )
        source_reliability = dataset.metadata.quality.reliability

        skipped_incomplete = 0
        skipped_duplicates = 0
        inserted = 0

        for raw in dataset.data:
            title = raw.get("title")
            source_name = (raw.get("source") or {}).get("name")
            published_at_raw = raw.get("publishedAt")
            if not title or not source_name or not published_at_raw:
                skipped_incomplete += 1
                continue

            cleaned_title = clean_article_text(title)
            raw_summary = raw.get("description")
            summary = clean_article_text(raw_summary) if raw_summary else None
            published_at = _parse_published_at(published_at_raw)
            processed = process_raw_article(
                title=cleaned_title,
                summary=summary,
                source=source_name,
                published_at=published_at,
                source_reliability=source_reliability,
            )

            if await self._articles.get_by_content_hash(processed.content_hash) is not None:
                skipped_duplicates += 1
                continue

            await self._articles.add(
                NewsArticle(
                    title=cleaned_title,
                    summary=summary,
                    source=source_name,
                    url=raw.get("url"),
                    published_at=published_at,
                    category=processed.category,
                    entities=processed.entities,
                    importance_score=processed.importance_score,
                    expected_volatility=processed.expected_volatility,
                    content_hash=processed.content_hash,
                )
            )
            inserted += 1

        logger.info(
            "news_ingestion_completed",
            query=query,
            requested=len(dataset.data),
            inserted=inserted,
            skipped_duplicates=skipped_duplicates,
            skipped_incomplete=skipped_incomplete,
        )
        return NewsIngestionResult(
            requested=len(dataset.data),
            skipped_duplicates=skipped_duplicates,
            skipped_incomplete=skipped_incomplete,
            inserted=inserted,
        )
