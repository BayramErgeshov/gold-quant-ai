"""Unit tests for `src.engines.book_engine.topic_classification`."""

from __future__ import annotations

import pytest

from src.engines.book_engine.topic_classification import classify_topics, primary_topic

pytestmark = pytest.mark.unit


def test_classify_topics_returns_empty_for_no_keyword_matches() -> None:
    assert classify_topics("The quick brown fox jumps over the lazy dog.") == []


def test_classify_topics_identifies_smart_money_topic() -> None:
    text = (
        "Institutional smart money often leaves an order block before a "
        "displacement move, creating an imbalance that later gets mitigated."
    )

    scores = classify_topics(text, max_topics=3)

    assert scores[0].topic == "smart_money"
    assert scores[0].score > 0


def test_classify_topics_respects_max_topics() -> None:
    text = (
        "Liquidity sweeps and stop hunts often precede a change of character "
        "in market structure, while the federal reserve raises interest rates "
        "amid persistent inflation."
    )

    scores = classify_topics(text, max_topics=2)

    assert len(scores) <= 2


def test_classify_topics_orders_by_score_descending() -> None:
    text = "gold gold gold liquidity"

    scores = classify_topics(text, max_topics=5)

    assert scores[0].topic == "gold"
    assert scores[0].score >= scores[-1].score


def test_primary_topic_returns_none_when_no_match() -> None:
    assert primary_topic("nothing relevant here") is None


def test_primary_topic_returns_highest_scoring_topic() -> None:
    assert primary_topic("wyckoff accumulation spring upthrust") == "wyckoff"
