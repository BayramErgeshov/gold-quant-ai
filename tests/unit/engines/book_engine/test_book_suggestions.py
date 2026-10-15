"""Unit tests for `src.engines.book_engine.book_suggestions`."""

from __future__ import annotations

import pytest

from src.engines.book_engine.book_suggestions import suggest_thin_topics
from src.engines.book_engine.topic_classification import TOPIC_KEYWORDS

pytestmark = pytest.mark.unit


def test_suggest_thin_topics_ranks_zero_coverage_topics_first() -> None:
    counts = {"gold": 500, "smart_money": 300}

    gaps = suggest_thin_topics(counts, max_suggestions=3)

    assert all(gap.chunk_count == 0 for gap in gaps)
    assert "gold" not in {gap.topic for gap in gaps}


def test_suggest_thin_topics_respects_max_suggestions() -> None:
    gaps = suggest_thin_topics({}, max_suggestions=2)

    assert len(gaps) == 2


def test_suggest_thin_topics_covers_only_known_taxonomy_topics() -> None:
    gaps = suggest_thin_topics({}, max_suggestions=len(TOPIC_KEYWORDS))

    assert {gap.topic for gap in gaps} <= set(TOPIC_KEYWORDS)


def test_suggest_thin_topics_orders_by_ascending_chunk_count() -> None:
    counts = {"gold": 10, "smart_money": 0, "liquidity": 5}

    gaps = suggest_thin_topics(counts, max_suggestions=3)

    assert [gap.chunk_count for gap in gaps] == sorted(gap.chunk_count for gap in gaps)
