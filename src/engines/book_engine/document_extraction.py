"""Multi-format document text/metadata extraction (Book Engine, Phase 23).

Extends `text_extraction.py`'s PDF-only extraction so the `/books` folder
watcher (`src.services.books.watcher`) can automatically ingest PDF,
EPUB, DOCX and TXT files, per the Institutional Knowledge Research
System spec: "automatically detect new PDF/EPUB/DOCX/TXT files." Each
format's own extractor produces the same `ExtractedPage` shape
`text_extraction.extract_pages` already produces for PDF, so
`BookIngestionPipeline` never needs to know which format a given file
came from.
"""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

import docx
import pypdf
from ebooklib import ITEM_DOCUMENT, epub

from src.engines.book_engine.text_extraction import ExtractedPage, extract_pages

SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({".pdf", ".epub", ".docx", ".txt"})


@dataclass(frozen=True, slots=True)
class DocumentMetadata:
    """Best-effort title/author recovered from a document's own metadata.

    Attributes:
        title: Embedded title, or the caller-supplied fallback if none
            was found — never a fabricated title.
        author: Embedded author, or "unknown" if none was found.
    """

    title: str
    author: str


class _HTMLTextExtractor(HTMLParser):
    """Strips tags from a single EPUB XHTML chapter, keeping only visible text."""

    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []

    def handle_data(self, data: str) -> None:
        self._chunks.append(data)

    def text(self) -> str:
        return "".join(self._chunks)


def _html_to_text(html: str) -> str:
    parser = _HTMLTextExtractor()
    parser.feed(html)
    return parser.text()


def _extract_txt_pages(path: Path) -> list[ExtractedPage]:
    text = path.read_text(encoding="utf-8", errors="replace")
    return [ExtractedPage(page_number=1, text=text, used_ocr=False)]


def _extract_docx_pages(path: Path) -> list[ExtractedPage]:
    document = docx.Document(str(path))
    text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    return [ExtractedPage(page_number=1, text=text, used_ocr=False)]


def _extract_epub_pages(path: Path) -> list[ExtractedPage]:
    book = epub.read_epub(str(path))
    pages: list[ExtractedPage] = []
    for index, item in enumerate(book.get_items_of_type(ITEM_DOCUMENT), start=1):
        html = item.get_content().decode("utf-8", errors="replace")
        pages.append(ExtractedPage(page_number=index, text=_html_to_text(html), used_ocr=False))
    return pages


def extract_document_pages(path: Path) -> list[ExtractedPage]:
    """Extract every page/section of a book, dispatching by file extension.

    Args:
        path: Path to a .pdf/.epub/.docx/.txt file.

    Returns:
        One `ExtractedPage` per page (PDF), per chapter (EPUB), or a
        single page covering the whole document (TXT/DOCX, which have no
        native page boundaries) — chunking downstream splits it further.

    Raises:
        FileNotFoundError: If `path` does not exist.
        ValueError: If `path`'s extension is not in `SUPPORTED_EXTENSIONS`.
    """
    if not path.exists():
        raise FileNotFoundError(f"Document not found: {path}")

    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return extract_pages(path)
    if suffix == ".txt":
        return _extract_txt_pages(path)
    if suffix == ".docx":
        return _extract_docx_pages(path)
    if suffix == ".epub":
        return _extract_epub_pages(path)
    raise ValueError(f"Unsupported document extension: {suffix!r}")


def extract_document_metadata(path: Path, *, fallback_title: str) -> DocumentMetadata:
    """Recover a document's own embedded title/author, never fabricating either.

    Args:
        path: Path to a .pdf/.epub/.docx/.txt file.
        fallback_title: Used when the document has no embedded title
            (typically the file's own stem).

    Returns:
        A `DocumentMetadata` with best-effort title/author, defaulting to
        `fallback_title`/"unknown" when nothing is embedded. TXT files
        carry no standard metadata format, so they always fall back.
    """
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        pdf_meta = pypdf.PdfReader(str(path)).metadata
        title = (pdf_meta.title if pdf_meta and pdf_meta.title else None) or fallback_title
        author = (pdf_meta.author if pdf_meta and pdf_meta.author else None) or "unknown"
        return DocumentMetadata(title=title, author=author)
    if suffix == ".docx":
        properties = docx.Document(str(path)).core_properties
        return DocumentMetadata(
            title=properties.title or fallback_title, author=properties.author or "unknown"
        )
    if suffix == ".epub":
        book = epub.read_epub(str(path))
        titles = book.get_metadata("DC", "title")
        authors = book.get_metadata("DC", "creator")
        title = titles[0][0] if titles else fallback_title
        author = authors[0][0] if authors else "unknown"
        return DocumentMetadata(title=title, author=author)
    return DocumentMetadata(title=fallback_title, author="unknown")
