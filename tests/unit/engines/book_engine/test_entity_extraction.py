"""Unit tests for `src.engines.book_engine.entity_extraction`."""

from __future__ import annotations

import pytest

from src.engines.book_engine.entity_extraction import extract_entities

pytestmark = pytest.mark.unit


def test_extract_entities_returns_empty_dict_for_no_matches() -> None:
    assert extract_entities("The quick brown fox jumps over the lazy dog.") == {}


def test_extract_entities_finds_currencies() -> None:
    entities = extract_entities("Gold priced in USD often correlates inversely with the dollar.")

    assert "USD" in entities["currencies"]


def test_extract_entities_finds_institutions() -> None:
    entities = extract_entities("The Federal Reserve raised rates at the last FOMC meeting.")

    assert "Federal Reserve" in entities["institutions"]
    assert "FOMC" in entities["institutions"]


def test_extract_entities_finds_indicators() -> None:
    entities = extract_entities("CPI came in hotter than expected, alongside weak Retail Sales.")

    assert "CPI" in entities["indicators"]
    assert "Retail Sales" in entities["indicators"]


def test_extract_entities_is_case_insensitive() -> None:
    entities = extract_entities("the federal reserve and the ecb both meet this week")

    assert "Federal Reserve" in entities["institutions"]
    assert "ECB" in entities["institutions"]


def test_extract_entities_uses_word_boundaries() -> None:
    # "GDP" should not match inside an unrelated longer word.
    entities = extract_entities("The word GDPositive does not contain the indicator.")

    assert "indicators" not in entities
