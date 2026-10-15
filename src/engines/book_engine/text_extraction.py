"""PDF text extraction with OCR fallback for scanned documents.

Per BOOK_RAG.md pipeline: "Import -> OCR if needed -> ...". Text-based PDF
pages are read directly via `pypdf`. A page whose extractable text layer is
too short (typically a scanned image) falls back to OCR via `pytesseract` +
`pdf2image`, which require the Tesseract and Poppler binaries to be
installed on the host. If they are unavailable, the affected page is
returned with empty text and a logged warning — never fabricated content
(DATA_QUALITY_STANDARD.md: "Never fabricate missing values").
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

import pypdf

from src.common.logging import get_logger

logger = get_logger(__name__)

_MIN_CHARS_FOR_TEXT_LAYER = 20


@dataclass(frozen=True, slots=True)
class ExtractedPage:
    """A single extracted PDF page.

    Attributes:
        page_number: 1-indexed page number.
        text: Extracted text, empty if extraction and OCR both failed.
        used_ocr: Whether OCR was used to produce `text`.
    """

    page_number: int
    text: str
    used_ocr: bool


def is_ocr_available() -> bool:
    """Check whether the Tesseract OCR binary is installed on this host.

    Returns:
        True if the `tesseract` executable is on PATH.
    """
    return shutil.which("tesseract") is not None


def _ocr_page(pdf_path: Path, page_number: int) -> str:  # pragma: no cover
    """Render a single PDF page to an image and OCR it.

    Not unit-tested directly (requires real Tesseract/Poppler binaries and
    a scanned PDF); covered by mocking this function in tests instead.
    """
    import pytesseract
    from pdf2image import convert_from_path

    images = convert_from_path(str(pdf_path), first_page=page_number, last_page=page_number)
    if not images:
        return ""
    return str(pytesseract.image_to_string(images[0], lang="eng+rus")).strip()


def extract_pages(pdf_path: Path) -> list[ExtractedPage]:
    """Extract text from every page of a PDF, using OCR for scanned pages.

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        One `ExtractedPage` per page.

    Raises:
        FileNotFoundError: If `pdf_path` does not exist.
    """
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    reader = pypdf.PdfReader(str(pdf_path))
    ocr_available = is_ocr_available()
    pages: list[ExtractedPage] = []

    for index, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        used_ocr = False

        if len(text) < _MIN_CHARS_FOR_TEXT_LAYER:
            if ocr_available:
                text = _ocr_page(pdf_path, index)
                used_ocr = True
            else:
                logger.warning("ocr_unavailable_skipping_page", page=index, pdf_path=str(pdf_path))

        pages.append(ExtractedPage(page_number=index, text=text, used_ocr=used_ocr))

    return pages
