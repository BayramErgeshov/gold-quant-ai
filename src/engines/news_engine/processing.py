"""End-to-end processing of a raw collected article into `NewsArticle` fields.

Combines classification, entity extraction, deduplication hashing and
importance/volatility scoring (NEWS_ENGINE.md "Processing Pipeline") into
a single step used by the ingestion service before persisting a
`NewsArticle`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.engines.book_engine.entity_extraction import extract_entities
from src.engines.news_engine.classification import classify_news_category
from src.engines.news_engine.deduplication import compute_content_hash
from src.engines.news_engine.scoring import compute_importance_score, expected_volatility


@dataclass(frozen=True, slots=True)
class ProcessedArticle:
    """Derived fields ready to populate a `NewsArticle` row."""

    category: str | None
    entities: dict[str, list[str]]
    importance_score: float
    expected_volatility: str
    content_hash: str


def process_raw_article(
    *,
    title: str,
    summary: str | None,
    source: str,
    published_at: datetime,
    source_reliability: float,
) -> ProcessedArticle:
    """Derive classification, entities, hash and scores for a raw article.

    Args:
        title: Article headline.
        summary: Article summary/body excerpt, if available.
        source: Publisher name, e.g. "reuters.com".
        published_at: Publication timestamp.
        source_reliability: The originating provider's reliability score
            in [0.0, 1.0] (`DataProvider.reliability`).

    Returns:
        A `ProcessedArticle` with the derived fields.
    """
    text = f"{title} {summary}" if summary else title

    category = classify_news_category(text)
    entities = extract_entities(text)
    entity_count = sum(len(matches) for matches in entities.values())

    return ProcessedArticle(
        category=category,
        entities=entities,
        importance_score=compute_importance_score(
            category=category,
            source_reliability=source_reliability,
            entity_count=entity_count,
        ),
        expected_volatility=expected_volatility(category),
        content_hash=compute_content_hash(
            title=title, source=source, published_at=published_at
        ),
    )
