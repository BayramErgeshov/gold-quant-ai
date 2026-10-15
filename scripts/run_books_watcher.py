"""Phase 23 Books folder watcher entrypoint.

Continuously polls the top-level `/books` folder for new PDF/EPUB/DOCX/TXT
files and ingests each one through the full Book Engine pipeline, per the
Institutional Knowledge Research System spec: "The system must
automatically re-analyze every new book without requiring user
interaction." A single flat drop folder (rather than a nested
`books/uploaded/`) so the user can just place a file in `/books` directly.

Run with the project's own virtual environment interpreter:

    PYTHONPATH=. ./.venv/Scripts/python.exe scripts/run_books_watcher.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from src.common.logging import configure_logging, get_logger
from src.core.embeddings.factory import get_embedding_provider
from src.database.postgres.session import get_session
from src.database.qdrant.client import get_qdrant_client
from src.engines.book_engine.book_suggestions import suggest_thin_topics
from src.repositories.book_chunk_repository import BookChunkRepository
from src.repositories.symbol_repository import SymbolRepository
from src.services.books.watcher import BooksFolderWatcher
from src.settings import get_settings

logger = get_logger(__name__)

_WATCHED_DIRECTORY = Path("books")
_SCAN_INTERVAL_SECONDS = 300


async def _log_topic_coverage_suggestions() -> None:
    """Log which of this platform's known topics the book library covers thinnest.

    Per the spec: "Suggest additional books that could improve the
    platform" — never a fabricated title, only a topic name from this
    platform's own taxonomy the user could look for a book on.
    """
    async with get_session() as session:
        counts = await BookChunkRepository(session).count_by_topic()

    gaps = suggest_thin_topics(counts)
    logger.info(
        "book_topic_coverage_suggestions",
        thin_topics=[{"topic": gap.topic, "chunk_count": gap.chunk_count} for gap in gaps],
    )


async def main() -> int:
    configure_logging(get_settings())
    _WATCHED_DIRECTORY.mkdir(parents=True, exist_ok=True)
    await _log_topic_coverage_suggestions()

    settings = get_settings()
    async with get_session() as session:
        symbol = await SymbolRepository(session).get_by_name(settings.platform.symbols.primary)
    claim_validation_symbol_id = symbol.id if symbol is not None else None
    if claim_validation_symbol_id is None:
        logger.warning("book_claim_validation_disabled", reason="symbol_not_seeded")

    watcher = BooksFolderWatcher(
        watched_directory=_WATCHED_DIRECTORY,
        embedding_provider=get_embedding_provider(),
        qdrant_client=get_qdrant_client(),
        session_factory=get_session,
        interval_seconds=_SCAN_INTERVAL_SECONDS,
        claim_validation_symbol_id=claim_validation_symbol_id,
    )
    logger.info(
        "books_watcher_started",
        watched_directory=str(_WATCHED_DIRECTORY),
        interval_seconds=_SCAN_INTERVAL_SECONDS,
        claim_validation_enabled=claim_validation_symbol_id is not None,
    )
    await watcher.run_forever()
    return 0  # pragma: no cover - unreachable: run_forever() loops until killed


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
