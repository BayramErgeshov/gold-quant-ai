"""Historical linking for news articles (NEWS_ENGINE.md "Historical Reaction").

A v1: finds prior articles in the same event category as evidence for the
Chief AI's "Historical Similarity" field. Measuring each linked article's
*actual* average/median/worst/best-case market reaction requires joining
against `src.engines.historical_engine.similarity_service` (candle data
around each article's timestamp) and is deferred until that cross-engine
integration is built — never approximated here.
"""

from __future__ import annotations

from src.models.news_article import NewsArticle
from src.repositories.news_article_repository import NewsArticleRepository

_DEFAULT_LIMIT = 10


async def find_related_articles(
    repository: NewsArticleRepository, article: NewsArticle, *, limit: int = _DEFAULT_LIMIT
) -> list[NewsArticle]:
    """Find prior articles in the same event category as the given article.

    Args:
        repository: Repository to query.
        article: The article to find historical context for. Must already
            be persisted (has a `published_at` and, optionally, `category`).
        limit: Maximum number of related articles to return.

    Returns:
        Prior articles sharing `article.category`, most recent first,
        excluding `article` itself. Empty if the article has no assigned
        category — never a fabricated "no related events" claim about an
        unclassified event.
    """
    if article.category is None:
        return []

    candidates = await repository.list_by_category(
        article.category, since=None, limit=limit + 1
    )
    return [candidate for candidate in candidates if candidate.id != article.id][:limit]
