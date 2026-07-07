"""Unit tests for `src.engines.book_engine.chunking`."""

from __future__ import annotations

import pytest

from src.engines.book_engine.chunking import chunk_page_text

pytestmark = pytest.mark.unit


def test_chunk_page_text_returns_empty_list_for_blank_input() -> None:
    assert chunk_page_text("") == []
    assert chunk_page_text("   \n\n   ") == []


def test_chunk_page_text_returns_single_chunk_for_short_text() -> None:
    text = "This is a short paragraph about order blocks."

    chunks = chunk_page_text(text, page=5)

    assert len(chunks) == 1
    assert chunks[0].page == 5
    assert chunks[0].text == text


def test_chunk_page_text_splits_long_text_into_multiple_chunks() -> None:
    words = " ".join(f"word{i}" for i in range(1000))

    chunks = chunk_page_text(words, target_words_per_chunk=400, overlap_words=50)

    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk.text.split()) <= 400


def test_chunk_page_text_overlaps_between_consecutive_chunks() -> None:
    words = " ".join(f"word{i}" for i in range(1000))

    chunks = chunk_page_text(words, target_words_per_chunk=400, overlap_words=50)

    first_chunk_words = chunks[0].text.split()
    second_chunk_words = chunks[1].text.split()
    assert first_chunk_words[-50:] == second_chunk_words[:50]


def test_chunk_page_text_covers_every_word_exactly_once_without_overlap() -> None:
    words = " ".join(f"word{i}" for i in range(100))

    chunks = chunk_page_text(words, target_words_per_chunk=40, overlap_words=0)

    reconstructed = " ".join(chunk.text for chunk in chunks)
    assert reconstructed == words
