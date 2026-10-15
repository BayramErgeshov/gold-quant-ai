"""Unit tests for `src.engines.book_engine.claim_direction`."""

from __future__ import annotations

import pytest

from src.engines.book_engine.claim_direction import classify_claim_direction

pytestmark = pytest.mark.unit


def test_classify_claim_direction_detects_bullish() -> None:
    statement = "An order block often signals a bullish reversal to the upside."

    assert classify_claim_direction(statement) == "bullish"


def test_classify_claim_direction_detects_bearish() -> None:
    statement = "A liquidity sweep above equal highs often precedes a bearish move downward."

    assert classify_claim_direction(statement) == "bearish"


def test_classify_claim_direction_neutral_with_no_keywords() -> None:
    statement = "Risk management is the foundation of long-term trading survival."

    assert classify_claim_direction(statement) == "neutral"


def test_classify_claim_direction_neutral_on_an_even_tie() -> None:
    statement = "This pattern can be bullish or bearish depending on context."

    assert classify_claim_direction(statement) == "neutral"
