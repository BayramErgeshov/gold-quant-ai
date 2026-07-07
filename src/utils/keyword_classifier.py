"""Generic keyword-based text classification.

Scores a piece of text against a taxonomy of named keyword lists and ranks
the matches. Shared by the Book Engine's topic classifier
(`src.engines.book_engine.topic_classification`) and the News Engine's
category classifier (`src.engines.news_engine.classification`) per
CODING_STANDARDS.md ("Never duplicate functionality"). Deliberately
explainable rather than a trained model — see each caller's module
docstring for the rationale.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class KeywordScore:
    """A single category's keyword-match score for a piece of text."""

    category: str
    score: float


def score_keywords(
    text: str, keyword_map: dict[str, tuple[str, ...]], *, max_categories: int = 3
) -> list[KeywordScore]:
    """Score and rank categories for a piece of text by keyword hit count.

    Args:
        text: Text to classify.
        keyword_map: Category name -> tuple of keyword phrases to search for.
        max_categories: Maximum number of categories to return.

    Returns:
        Up to `max_categories` `KeywordScore`, sorted by score descending,
        excluding categories with zero keyword hits. Empty if nothing matches.
    """
    normalized = text.lower()
    scores = [
        KeywordScore(category=category, score=float(hits))
        for category, keywords in keyword_map.items()
        if (hits := sum(len(re.findall(re.escape(keyword), normalized)) for keyword in keywords))
        > 0
    ]
    scores.sort(key=lambda item: item.score, reverse=True)
    return scores[:max_categories]


def primary_category(text: str, keyword_map: dict[str, tuple[str, ...]]) -> str | None:
    """Return only the single highest-scoring category for a piece of text.

    Args:
        text: Text to classify.
        keyword_map: Category name -> tuple of keyword phrases to search for.

    Returns:
        The highest-scoring category name, or None if nothing matched.
    """
    scores = score_keywords(text, keyword_map, max_categories=1)
    return scores[0].category if scores else None
