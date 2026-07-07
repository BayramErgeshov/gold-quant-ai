"""Chunking of extracted book text (BOOK_RAG.md: "Chunking").

Per BOOK_RAG.md: "Books must never be processed as a single document...
Each chunk should contain one complete idea." This is a word-window
chunker with overlap: paragraphs are preserved as unit boundaries where
possible, packed up to a target word count, with a trailing overlap
carried into the next chunk so context is not lost at boundaries. Word
count is used as a tokenizer-free approximation of
`config/books.yaml` `chunking.target_tokens_per_chunk`, appropriate for a
local, provider-agnostic embedding pipeline (no dependency on any single
provider's tokenizer).
"""

from __future__ import annotations

from dataclasses import dataclass

_PARAGRAPH_SEPARATOR = "\n\n"


@dataclass(frozen=True, slots=True)
class TextChunk:
    """A single chunk of book text ready for embedding.

    Attributes:
        text: The chunk's text content.
        page: Source page number, if known.
    """

    text: str
    page: int | None = None


def _split_into_paragraphs(text: str) -> list[str]:
    paragraphs = text.split(_PARAGRAPH_SEPARATOR)
    return [paragraph.strip() for paragraph in paragraphs if paragraph.strip()]


def chunk_page_text(
    text: str,
    *,
    page: int | None = None,
    target_words_per_chunk: int = 400,
    overlap_words: int = 50,
) -> list[TextChunk]:
    """Split a page's text into overlapping, target-sized word-window chunks.

    Args:
        text: Raw extracted page text.
        page: Source page number, attached to every resulting chunk.
        target_words_per_chunk: Approximate target chunk size, in words.
        overlap_words: Number of trailing words repeated at the start of
            the next chunk.

    Returns:
        A list of `TextChunk`, in order. Empty/whitespace-only input
        yields an empty list.
    """
    words = " ".join(_split_into_paragraphs(text)).split()
    if not words:
        return []

    chunks: list[TextChunk] = []
    start = 0
    while start < len(words):
        end = min(start + target_words_per_chunk, len(words))
        chunks.append(TextChunk(text=" ".join(words[start:end]), page=page))
        if end == len(words):
            break
        start = end - overlap_words if end - overlap_words > start else end

    return chunks
