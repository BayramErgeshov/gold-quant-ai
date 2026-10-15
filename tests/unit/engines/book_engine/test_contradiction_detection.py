"""Unit tests for `src.engines.book_engine.contradiction_detection`."""

from __future__ import annotations

import uuid

import pytest

from src.engines.book_engine.contradiction_detection import (
    find_agreements,
    find_contradictions,
)
from src.models.book_claim import BookClaim

pytestmark = pytest.mark.unit


def _claim(*, topic: str | None, statement: str) -> BookClaim:
    return BookClaim(
        id=uuid.uuid4(),
        book_id=uuid.uuid4(),
        chunk_id=uuid.uuid4(),
        statement=statement,
        topic=topic,
    )


def test_find_agreements_groups_same_topic_and_direction() -> None:
    claims = [
        _claim(topic="smart_money", statement="Order blocks often signal a bullish reversal up."),
        _claim(
            topic="smart_money", statement="Institutional buying tends to precede upward moves."
        ),
    ]

    agreements = find_agreements(claims)

    assert len(agreements) == 1
    assert agreements[0].topic == "smart_money"
    assert agreements[0].direction == "bullish"
    assert len(agreements[0].claim_ids) == 2


def test_find_agreements_ignores_a_single_claim() -> None:
    claims = [_claim(topic="smart_money", statement="Order blocks often signal a bullish move.")]

    assert find_agreements(claims) == []


def test_find_agreements_ignores_claims_without_a_topic_or_direction() -> None:
    claims = [
        _claim(topic=None, statement="Order blocks often signal a bullish move up."),
        _claim(topic="smart_money", statement="Risk management preserves capital over time."),
    ]

    assert find_agreements(claims) == []


def test_find_contradictions_detects_opposing_directions_on_the_same_topic() -> None:
    claims = [
        _claim(topic="liquidity", statement="A liquidity sweep often precedes a bullish move up."),
        _claim(
            topic="liquidity",
            statement="A liquidity sweep often precedes a bearish move downward.",
        ),
    ]

    contradictions = find_contradictions(claims)

    assert len(contradictions) == 1
    assert contradictions[0].topic == "liquidity"
    assert len(contradictions[0].bullish_claim_ids) == 1
    assert len(contradictions[0].bearish_claim_ids) == 1


def test_find_contradictions_empty_when_all_claims_agree() -> None:
    claims = [
        _claim(topic="liquidity", statement="A liquidity sweep often precedes a bullish move up."),
        _claim(topic="liquidity", statement="Sweeps usually signal a bullish reversal higher."),
    ]

    assert find_contradictions(claims) == []
