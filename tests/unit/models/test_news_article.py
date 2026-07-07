"""Unit tests for the `NewsArticle` ORM model."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.models.news_article import NewsArticle

pytestmark = pytest.mark.unit


def test_repr_includes_title_and_source() -> None:
    article = NewsArticle(
        title="Fed holds rates steady",
        source="reuters.com",
        published_at=datetime(2026, 1, 1, tzinfo=UTC),
        content_hash="abc123",
    )

    assert repr(article) == "NewsArticle(title='Fed holds rates steady', source='reuters.com')"
