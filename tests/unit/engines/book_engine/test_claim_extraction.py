"""Unit tests for `src.engines.book_engine.claim_extraction`."""

from __future__ import annotations

import pytest

from src.engines.book_engine.claim_extraction import extract_claims

pytestmark = pytest.mark.unit


def test_extract_claims_returns_empty_for_text_with_no_markers() -> None:
    text = "This chapter introduces the order block concept. It is a simple idea."

    assert extract_claims(text) == []


def test_extract_claims_finds_a_sentence_with_a_frequency_marker() -> None:
    text = (
        "Order blocks tend to precede a strong displacement move. "
        "This is just background context with no checkable marker here."
    )

    claims = extract_claims(text)

    assert len(claims) == 1
    assert "tend to precede" in claims[0]


def test_extract_claims_finds_a_sentence_with_a_percentage() -> None:
    text = "Backtests show this setup wins 62% of the time across major pairs."

    claims = extract_claims(text)

    assert len(claims) == 1
    assert "62%" in claims[0]


def test_extract_claims_skips_sentences_that_are_too_short() -> None:
    text = "It works often."

    assert extract_claims(text) == []


def test_extract_claims_deduplicates_repeated_sentences() -> None:
    sentence = "Liquidity sweeps often precede a genuine reversal in price."
    text = f"{sentence} {sentence}"

    assert extract_claims(text) == [sentence]


def test_extract_claims_handles_multiple_qualifying_sentences() -> None:
    text = (
        "Smart money usually accumulates before a breakout occurs. "
        "Retail traders typically chase price after the move already happened."
    )

    claims = extract_claims(text)

    assert len(claims) == 2
