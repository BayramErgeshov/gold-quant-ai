"""Unit tests for news category classification."""

from __future__ import annotations

import pytest

from src.engines.news_engine.classification import classify_news_category

pytestmark = pytest.mark.unit


def test_classifies_central_bank_news() -> None:
    assert classify_news_category("Federal Reserve holds rates steady") == "central_bank"


def test_classifies_inflation_news() -> None:
    assert classify_news_category("US CPI rises more than expected") == "inflation"


def test_classifies_employment_news() -> None:
    assert classify_news_category("Nonfarm payrolls beat estimates") == "employment"


def test_classifies_geopolitics_news() -> None:
    assert classify_news_category("Ceasefire talks collapse amid new sanctions") == "geopolitics"


def test_returns_none_for_unrelated_text() -> None:
    assert classify_news_category("Local bakery wins a baking competition") is None
