"""Unit tests for `Book` and `BookChunk` ORM models."""

from __future__ import annotations

import uuid

import pytest

from src.models.book import Book, BookChunk

pytestmark = pytest.mark.unit


def test_book_repr_includes_title_and_author() -> None:
    book = Book(
        title="Trading in the Zone",
        author="Mark Douglas",
        source_path="books/uploaded/trading_in_the_zone.pdf",
    )

    assert repr(book) == "Book(title='Trading in the Zone', author='Mark Douglas')"


def test_book_chunk_repr_includes_book_id_page_and_topic() -> None:
    book_id = uuid.uuid4()
    chunk = BookChunk(book_id=book_id, page=42, text="...", topic="risk")

    assert repr(chunk) == f"BookChunk(book_id={book_id}, page=42, topic='risk')"
