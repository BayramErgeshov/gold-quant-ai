"""Unit tests for `src.engines.book_engine.text_extraction`."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.engines.book_engine.text_extraction import extract_pages, is_ocr_available

pytestmark = pytest.mark.unit


def _fake_page(text: str) -> MagicMock:
    page = MagicMock()
    page.extract_text.return_value = text
    return page


def test_extract_pages_raises_for_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        extract_pages(tmp_path / "does_not_exist.pdf")


def test_extract_pages_uses_text_layer_when_present(tmp_path: Path) -> None:
    pdf_path = tmp_path / "book.pdf"
    pdf_path.write_bytes(b"fake pdf bytes")
    reader = MagicMock()
    reader.pages = [_fake_page("A" * 100), _fake_page("B" * 50)]

    with (
        patch("src.engines.book_engine.text_extraction.pypdf.PdfReader", return_value=reader),
        patch("src.engines.book_engine.text_extraction.is_ocr_available", return_value=True),
    ):
        pages = extract_pages(pdf_path)

    assert len(pages) == 2
    assert pages[0].text == "A" * 100
    assert pages[0].used_ocr is False
    assert pages[1].used_ocr is False


def test_extract_pages_falls_back_to_ocr_for_short_text(tmp_path: Path) -> None:
    pdf_path = tmp_path / "scanned.pdf"
    pdf_path.write_bytes(b"fake pdf bytes")
    reader = MagicMock()
    reader.pages = [_fake_page("")]

    with (
        patch("src.engines.book_engine.text_extraction.pypdf.PdfReader", return_value=reader),
        patch("src.engines.book_engine.text_extraction.is_ocr_available", return_value=True),
        patch(
            "src.engines.book_engine.text_extraction._ocr_page",
            return_value="ocr recovered text",
        ),
    ):
        pages = extract_pages(pdf_path)

    assert pages[0].text == "ocr recovered text"
    assert pages[0].used_ocr is True


def test_extract_pages_skips_page_when_ocr_unavailable(tmp_path: Path) -> None:
    pdf_path = tmp_path / "scanned.pdf"
    pdf_path.write_bytes(b"fake pdf bytes")
    reader = MagicMock()
    reader.pages = [_fake_page("")]

    with (
        patch("src.engines.book_engine.text_extraction.pypdf.PdfReader", return_value=reader),
        patch("src.engines.book_engine.text_extraction.is_ocr_available", return_value=False),
    ):
        pages = extract_pages(pdf_path)

    assert pages[0].text == ""
    assert pages[0].used_ocr is False


def test_is_ocr_available_reflects_tesseract_on_path() -> None:
    with patch("src.engines.book_engine.text_extraction.shutil.which", return_value=None):
        assert is_ocr_available() is False

    with patch(
        "src.engines.book_engine.text_extraction.shutil.which", return_value="/usr/bin/tesseract"
    ):
        assert is_ocr_available() is True
