"""Text cleaning for extracted book pages (BOOK_RAG.md pipeline: "Cleaning")."""

from __future__ import annotations

import re

_WHITESPACE_RUN = re.compile(r"[ \t]+")
_BLANK_LINE_RUN = re.compile(r"\n{3,}")


def clean_text(text: str) -> str:
    """Normalize whitespace in raw extracted text.

    Args:
        text: Raw text extracted from a PDF page (via text layer or OCR).

    Returns:
        Text with collapsed horizontal whitespace and at most one blank
        line between paragraphs, leading/trailing whitespace stripped.
    """
    normalized = _WHITESPACE_RUN.sub(" ", text)
    normalized = _BLANK_LINE_RUN.sub("\n\n", normalized)
    return normalized.strip()
