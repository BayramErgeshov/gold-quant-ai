"""Unit tests for news article text cleaning."""

from __future__ import annotations

import pytest

from src.engines.news_engine.cleaning import clean_article_text

pytestmark = pytest.mark.unit


def test_strips_newsapi_truncation_marker() -> None:
    assert clean_article_text("Fed holds rates steady... [+1234 chars]") == (
        "Fed holds rates steady..."
    )


def test_strips_truncation_marker_with_parentheses() -> None:
    assert clean_article_text("Gold rallies on inflation data (+500 chars)") == (
        "Gold rallies on inflation data"
    )


def test_collapses_irregular_whitespace() -> None:
    assert clean_article_text("Fed  holds\n\nrates   steady") == "Fed holds rates steady"


def test_strips_leading_and_trailing_whitespace() -> None:
    assert clean_article_text("  Fed holds rates steady  ") == "Fed holds rates steady"


def test_leaves_clean_text_unchanged() -> None:
    assert clean_article_text("Fed holds rates steady") == "Fed holds rates steady"
