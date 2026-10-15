"""Unit tests for news importance/volatility scoring."""

from __future__ import annotations

import pytest

from src.engines.news_engine.scoring import compute_importance_score, expected_volatility

pytestmark = pytest.mark.unit


def test_high_impact_category_has_high_volatility() -> None:
    assert expected_volatility("central_bank") == "high"


def test_medium_impact_category_has_medium_volatility() -> None:
    assert expected_volatility("inflation") == "medium"


def test_unclassified_category_has_low_volatility() -> None:
    assert expected_volatility(None) == "low"


def test_unknown_category_has_low_volatility() -> None:
    assert expected_volatility("unmapped_category") == "low"


def test_importance_score_increases_with_category_impact() -> None:
    high = compute_importance_score(category="central_bank", source_reliability=0.5, entity_count=0)
    low = compute_importance_score(category=None, source_reliability=0.5, entity_count=0)

    assert high > low


def test_importance_score_increases_with_source_reliability() -> None:
    reliable = compute_importance_score(category=None, source_reliability=1.0, entity_count=0)
    unreliable = compute_importance_score(category=None, source_reliability=0.0, entity_count=0)

    assert reliable > unreliable


def test_importance_score_increases_with_entity_count() -> None:
    rich = compute_importance_score(category=None, source_reliability=0.5, entity_count=10)
    sparse = compute_importance_score(category=None, source_reliability=0.5, entity_count=0)

    assert rich > sparse


def test_importance_score_is_capped_at_one() -> None:
    score = compute_importance_score(
        category="central_bank", source_reliability=1.0, entity_count=100
    )

    assert score == 1.0
