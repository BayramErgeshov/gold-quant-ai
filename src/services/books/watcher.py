"""Books folder watcher (Institutional Knowledge Research System, Phase 23).

Per the spec: "Automatically detect new PDF/EPUB/DOCX/TXT files... On
detection: read the entire book completely... The system must
automatically re-analyze every new book without requiring user
interaction." Polls the watched folder (the top-level `/books` drop
folder, per `scripts/run_books_watcher.py`) for supported files not yet
ingested and runs each one through `BookIngestionPipeline`, using the
same polling-loop pattern
`src.services.scheduler.live_loop.LiveTradingLoop` already uses for
market cycles — consistent with the rest of this platform's architecture,
and trivially testable without OS-specific filesystem-event mocking.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from pathlib import Path

from qdrant_client import AsyncQdrantClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.common.logging import get_logger
from src.core.embeddings.provider import EmbeddingProvider
from src.engines.book_engine.claim_validation import ClaimValidationResult, ClaimValidationService
from src.engines.book_engine.document_extraction import SUPPORTED_EXTENSIONS
from src.engines.book_engine.pipeline import BookIngestionPipeline
from src.models.book import Book
from src.repositories.book_chunk_repository import BookChunkRepository
from src.repositories.book_claim_repository import BookClaimRepository
from src.repositories.book_repository import BookRepository
from src.repositories.candle_repository import CandleRepository
from src.repositories.concept_repository import ConceptRelationshipRepository, ConceptRepository
from src.repositories.runtime_settings_repository import RuntimeSettingsRepository

logger = get_logger(__name__)

# Per the "Books" production requirement: "Backtest every extracted
# hypothesis." M15 with a deep window mirrors the primary engine's own
# analysis timeframe -- the only market this platform has deep enough
# history to test a claim against today.
_CLAIM_VALIDATION_TIMEFRAME = "M15"
_CLAIM_VALIDATION_CANDLE_COUNT = 2000
# Processed gradually across cycles rather than the entire pending queue
# at once -- this platform has 10,000+ pending claims and re-validating
# all of them every cycle would make each scan far too slow.
_CLAIM_VALIDATION_BATCH_SIZE = 200


@dataclass(slots=True)
class BooksScanResult:
    """Outcome of a single folder scan-and-ingest cycle.

    Attributes:
        discovered: Every supported file found in the watched folder this cycle.
        ingested: Files newly ingested this cycle (excludes already-known ones).
        errors: `{file_path: error_message}` for any file whose ingestion raised.
        claim_validations: This cycle's batch of book-claim validation
            outcomes (`src.engines.book_engine.claim_validation`), empty
            if no `symbol_id` was configured for validation.
    """

    discovered: list[Path] = field(default_factory=list)
    ingested: list[Path] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)
    claim_validations: list[ClaimValidationResult] = field(default_factory=list)


class BooksFolderWatcher:
    """Polls a folder for new PDF/EPUB/DOCX/TXT files and ingests each one."""

    def __init__(
        self,
        *,
        watched_directory: Path,
        embedding_provider: EmbeddingProvider,
        qdrant_client: AsyncQdrantClient,
        session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]],
        interval_seconds: int,
        claim_validation_symbol_id: uuid.UUID | None = None,
    ) -> None:
        """Initialize the watcher (constructor injection).

        Args:
            watched_directory: Folder to poll for new documents (typically
                the top-level `/books` drop folder).
            embedding_provider: Active embedding backend, passed through
                to each `BookIngestionPipeline` cycle.
            qdrant_client: Active Qdrant client for vector storage.
            session_factory: Callable returning a fresh `AsyncSession`
                context manager per cycle (e.g.
                `src.database.postgres.session.get_session`).
            claim_validation_symbol_id: The primary symbol (e.g. XAUUSD)
                to backtest pending book claims against
                (`src.engines.book_engine.claim_validation`), per the
                "Books" production requirement's "Backtest every
                extracted hypothesis." None disables claim validation --
                e.g. before the symbol is seeded.
            interval_seconds: Delay between the end of one scan and the
                start of the next.
        """
        self._watched_directory = watched_directory
        self._embedding_provider = embedding_provider
        self._qdrant = qdrant_client
        self._session_factory = session_factory
        self._interval_seconds = interval_seconds
        self._claim_validation_symbol_id = claim_validation_symbol_id

    async def run_forever(self) -> None:
        """Run scan cycles back to back, forever, sleeping `interval_seconds` between them."""
        while True:
            await self.scan_once()
            await asyncio.sleep(self._interval_seconds)

    async def scan_once(self) -> BooksScanResult:
        """Run exactly one scan-and-ingest cycle.

        Never raises for an individual file's failure: one malformed
        document must not block every other book in the folder from
        being ingested this cycle. Each book is ingested and committed in
        its own session -- an institutional audit finding: running every
        book in one shared, single-commit session meant a crash (or an
        unhandled exception outside the per-file try/except, e.g. a
        connection drop) partway through the folder discarded every
        already-ingested book's work too, the same failure class already
        found and fixed once for `LiveTradingLoop.run_once` (which splits
        position monitoring and the market scan into their own sessions
        for the identical reason).

        Returns:
            A `BooksScanResult` summarizing what was found, newly
            ingested, and any per-file errors.
        """
        result = BooksScanResult()
        watched_directory = await self._resolve_watched_directory()
        if not watched_directory.is_dir():
            logger.warning("books_watched_directory_missing", path=str(watched_directory))
            return result

        result.discovered = sorted(
            path
            for path in watched_directory.iterdir()
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
        )

        for path in result.discovered:
            try:
                book = await self._ingest_one(path)
            except Exception as exc:
                result.errors[str(path)] = str(exc)
                logger.exception("books_watcher_ingestion_failed", path=str(path))
                continue
            if book is None:
                continue
            result.ingested.append(path)
            logger.info(
                "books_watcher_ingested_new_book",
                path=str(path),
                book_id=str(book.id),
                title=book.title,
            )

        result.claim_validations = await self._validate_pending_claims()
        return result

    async def _validate_pending_claims(self) -> list[ClaimValidationResult]:
        """Backtest a batch of pending book claims against real price history.

        Per the "Books" production requirement: "Backtest every extracted
        hypothesis." Never raises: a validation failure must not block
        book ingestion, and no claim is ever marked accepted/rejected
        without going through `ClaimValidationService`'s own real
        historical-signal backtest.
        """
        if self._claim_validation_symbol_id is None:
            return []
        try:
            async with self._session_factory() as session:
                candles = await CandleRepository(session).list_most_recent(
                    self._claim_validation_symbol_id,
                    _CLAIM_VALIDATION_TIMEFRAME,
                    count=_CLAIM_VALIDATION_CANDLE_COUNT,
                )
                service = ClaimValidationService(claim_repository=BookClaimRepository(session))
                return await service.validate_pending_claims(
                    candles, limit=_CLAIM_VALIDATION_BATCH_SIZE
                )
        except Exception:
            logger.exception("book_claim_validation_failed")
            return []

    async def _resolve_watched_directory(self) -> Path:
        """Resolve this cycle's watched directory, honoring a "Books Folder" override.

        Per the "Settings" production requirement: "Books Folder" must be
        changeable from the interface -- `RuntimeSettings.books_folder` is
        re-read every cycle, mirroring how `LiveTradingLoop` re-reads its
        own settings, so a change takes effect on the very next scan
        without a restart.
        """
        async with self._session_factory() as session:
            row = await RuntimeSettingsRepository(session).get_or_create_default()
        if row.books_folder:
            return Path(row.books_folder)
        return self._watched_directory

    async def _ingest_one(self, path: Path) -> Book | None:
        """Ingest a single book in its own committed session.

        Returns:
            The ingested `Book`, or None if `path` was already known
            (skipped, not an error).
        """
        async with self._session_factory() as session:
            book_repository = BookRepository(session)
            if await book_repository.get_by_source_path(str(path)) is not None:
                return None
            pipeline = BookIngestionPipeline(
                book_repository=book_repository,
                chunk_repository=BookChunkRepository(session),
                claim_repository=BookClaimRepository(session),
                concept_repository=ConceptRepository(session),
                concept_relationship_repository=ConceptRelationshipRepository(session),
                embedding_provider=self._embedding_provider,
                qdrant_client=self._qdrant,
            )
            return await pipeline.ingest(path)
