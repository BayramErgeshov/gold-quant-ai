"""Unit tests for `src.utils.keyword_classifier`."""

from __future__ import annotations

import pytest

from src.utils.keyword_classifier import primary_category, score_keywords

pytestmark = pytest.mark.unit

_KEYWORD_MAP = {
    "fruit": ("apple", "banana"),
    "vegetable": ("carrot", "potato"),
}


def test_score_keywords_returns_empty_for_no_matches() -> None:
    assert score_keywords("nothing relevant here", _KEYWORD_MAP) == []


def test_score_keywords_ranks_by_hit_count() -> None:
    text = "apple apple banana carrot"

    scores = score_keywords(text, _KEYWORD_MAP, max_categories=2)

    assert scores[0].category == "fruit"
    assert scores[0].score == 3.0
    assert scores[1].category == "vegetable"
    assert scores[1].score == 1.0


def test_score_keywords_respects_max_categories() -> None:
    text = "apple carrot"

    scores = score_keywords(text, _KEYWORD_MAP, max_categories=1)

    assert len(scores) == 1


def test_primary_category_returns_none_for_no_match() -> None:
    assert primary_category("nothing relevant", _KEYWORD_MAP) is None


def test_primary_category_returns_highest_scoring() -> None:
    assert primary_category("apple banana carrot", _KEYWORD_MAP) == "fruit"
