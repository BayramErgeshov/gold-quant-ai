"""Language detection for ingested documents (BOOK_RAG.md: "Language Detection")."""

from __future__ import annotations

from langdetect import LangDetectException, detect

from src.common.logging import get_logger

logger = get_logger(__name__)

DEFAULT_LANGUAGE = "en"


def detect_language(text: str) -> str:
    """Detect the ISO 639-1 language code of a text sample.

    Args:
        text: Text to analyze; a few sentences give more reliable results
            than a handful of words.

    Returns:
        An ISO 639-1 language code, e.g. "en", "ru". Falls back to
        `DEFAULT_LANGUAGE` when detection fails (empty/too-short/ambiguous
        text) rather than raising — a failed language guess must never
        block book ingestion.
    """
    if not text.strip():
        return DEFAULT_LANGUAGE
    try:
        return str(detect(text))
    except LangDetectException:
        logger.warning("language_detection_failed", text_sample=text[:50])
        return DEFAULT_LANGUAGE
