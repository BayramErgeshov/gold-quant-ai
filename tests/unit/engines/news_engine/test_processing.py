"""Unit tests for the raw-article processing orchestrator."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.engines.news_engine.processing import process_raw_article

pytestmark = pytest.mark.unit

_PUBLISHED_AT = datetime(2026, 1, 1, tzinfo=UTC)


def test_processes_central_bank_article_with_entities() -> None:
    result = process_raw_article(
        title="Federal Reserve holds interest rates steady",
        summary="The FOMC decision affects USD and gold markets.",
        source="reuters.com",
        published_at=_PUBLISHED_AT,
        source_reliability=0.9,
    )

    assert result.category == "central_bank"
    assert result.expected_volatility == "high"
    assert "currencies" in result.entities
    assert "institutions" in result.entities
    assert result.importance_score > 0.5
    assert len(result.content_hash) == 64


def test_processes_unclassified_article_without_summary() -> None:
    result = process_raw_article(
        title="Local bakery wins a baking competition",
        summary=None,
        source="localnews.com",
        published_at=_PUBLISHED_AT,
        source_reliability=0.5,
    )

    assert result.category is None
    assert result.expected_volatility == "low"
    assert result.entities == {}


def test_content_hash_matches_direct_computation() -> None:
    from src.engines.news_engine.deduplication import compute_content_hash

    result = process_raw_article(
        title="Fed holds rates steady",
        summary=None,
        source="reuters.com",
        published_at=_PUBLISHED_AT,
        source_reliability=0.8,
    )

    expected = compute_content_hash(
        title="Fed holds rates steady", source="reuters.com", published_at=_PUBLISHED_AT
    )
    assert result.content_hash == expected
