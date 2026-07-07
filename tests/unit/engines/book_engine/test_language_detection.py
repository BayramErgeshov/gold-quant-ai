"""Unit tests for `src.engines.book_engine.language_detection`."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from langdetect import LangDetectException

from src.engines.book_engine.language_detection import DEFAULT_LANGUAGE, detect_language

pytestmark = pytest.mark.unit


def test_detect_language_returns_default_for_empty_text() -> None:
    assert detect_language("") == DEFAULT_LANGUAGE
    assert detect_language("   ") == DEFAULT_LANGUAGE


def test_detect_language_returns_detected_code_for_english_text() -> None:
    text = (
        "Order blocks are areas on a price chart where institutional traders "
        "have historically placed large orders, influencing future price action."
    )

    assert detect_language(text) == "en"


def test_detect_language_falls_back_on_detection_failure() -> None:
    with patch(
        "src.engines.book_engine.language_detection.detect",
        side_effect=LangDetectException(1, "no features in text"),
    ):
        assert detect_language("some text") == DEFAULT_LANGUAGE
