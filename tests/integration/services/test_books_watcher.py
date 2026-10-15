"""Integration tests for `BooksFolderWatcher` (Phase 23)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.models.book_claim import BookClaim
from src.models.candle import Candle
from src.models.symbol import Symbol
from src.repositories.book_claim_repository import BookClaimRepository
from src.repositories.book_repository import BookRepository
from src.repositories.candle_repository import CandleRepository
from src.repositories.runtime_settings_repository import RuntimeSettingsRepository
from src.repositories.symbol_repository import SymbolRepository
from src.services.books.watcher import BooksFolderWatcher
from tests.integration.book_engine._fakes import FakeEmbeddingProvider, FakeQdrantClient

pytestmark = pytest.mark.asyncio


def _committing_session_factory(
    engine: AsyncEngine,
) -> Callable[[], AbstractAsyncContextManager[AsyncSession]]:
    raw_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    @asynccontextmanager
    async def commit_on_exit() -> AsyncIterator[AsyncSession]:
        async with raw_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    return commit_on_exit


def _watcher(directory: Path, engine: AsyncEngine, qdrant: FakeQdrantClient) -> BooksFolderWatcher:
    return BooksFolderWatcher(
        watched_directory=directory,
        embedding_provider=FakeEmbeddingProvider(dimension=8),
        qdrant_client=qdrant,  # type: ignore[arg-type]
        session_factory=_committing_session_factory(engine),
        interval_seconds=60,
    )


async def test_scan_once_ingests_every_supported_file_in_the_folder(
    engine: AsyncEngine, tmp_path: Path
) -> None:
    (tmp_path / "notes.txt").write_text(
        "Risk management is the foundation of longevity in trading."
    )
    (tmp_path / "ignore_me.jpg").write_bytes(b"not a book")

    result = await _watcher(tmp_path, engine, FakeQdrantClient()).scan_once()

    assert result.discovered == [tmp_path / "notes.txt"]
    assert result.ingested == [tmp_path / "notes.txt"]
    assert result.errors == {}

    raw_session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with raw_session_factory() as check_session:
        book = await BookRepository(check_session).get_by_source_path(str(tmp_path / "notes.txt"))
    assert book is not None
    assert book.title == "notes"
    assert book.author == "unknown"


async def test_scan_once_skips_files_already_ingested_in_a_previous_cycle(
    engine: AsyncEngine, tmp_path: Path
) -> None:
    (tmp_path / "notes.txt").write_text("Position sizing must scale with volatility.")
    watcher = _watcher(tmp_path, engine, FakeQdrantClient())

    first = await watcher.scan_once()
    second = await watcher.scan_once()

    assert first.ingested == [tmp_path / "notes.txt"]
    assert second.discovered == [tmp_path / "notes.txt"]
    assert second.ingested == []

    raw_session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with raw_session_factory() as check_session:
        all_books = await BookRepository(check_session).list_all()
    assert len(all_books) == 1


async def test_scan_once_isolates_a_single_files_failure(
    engine: AsyncEngine, tmp_path: Path
) -> None:
    (tmp_path / "good.txt").write_text("A good, real book about market structure.")
    broken_docx = tmp_path / "broken.docx"
    broken_docx.write_bytes(b"not a real docx file")

    result = await _watcher(tmp_path, engine, FakeQdrantClient()).scan_once()

    assert result.ingested == [tmp_path / "good.txt"]
    assert str(broken_docx) in result.errors

    raw_session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with raw_session_factory() as check_session:
        all_books = await BookRepository(check_session).list_all()
    assert len(all_books) == 1


async def test_scan_once_returns_empty_result_when_directory_is_missing(
    engine: AsyncEngine, tmp_path: Path
) -> None:
    missing = tmp_path / "does_not_exist"

    result = await _watcher(missing, engine, FakeQdrantClient()).scan_once()

    assert result.discovered == []
    assert result.ingested == []
    assert result.errors == {}


async def test_scan_once_honors_a_books_folder_setting_override(
    engine: AsyncEngine, tmp_path: Path
) -> None:
    default_directory = tmp_path / "default"
    default_directory.mkdir()
    override_directory = tmp_path / "override"
    override_directory.mkdir()
    (override_directory / "notes.txt").write_text("A book placed in the overridden folder.")

    raw_session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with raw_session_factory() as setup_session:
        repository = RuntimeSettingsRepository(setup_session)
        row = await repository.get_or_create_default()
        row.books_folder = str(override_directory)
        await repository.add(row)
        await setup_session.commit()

    result = await _watcher(default_directory, engine, FakeQdrantClient()).scan_once()

    assert result.discovered == [override_directory / "notes.txt"]
    assert result.ingested == [override_directory / "notes.txt"]


async def test_scan_once_validates_pending_book_claims_when_a_symbol_is_configured(
    engine: AsyncEngine, tmp_path: Path
) -> None:
    # Per the "Books" production requirement: "Backtest every extracted
    # hypothesis." A claim on a testable topic (see
    # `src.engines.book_engine.claim_validation._TOPIC_AGENTS`) must be
    # picked up and validated once a symbol is configured, without
    # needing any book to actually be dropped in the folder this cycle.
    raw_session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with raw_session_factory() as setup_session:
        symbol = await SymbolRepository(setup_session).add(
            Symbol(name="XAUUSD", display_name="Gold")
        )
        base_time = datetime(2026, 1, 1, tzinfo=UTC)
        candles = [
            Candle(
                symbol_id=symbol.id,
                timeframe="M15",
                timestamp=base_time + timedelta(minutes=15 * i),
                open=2000.0 + i * 0.5,
                high=2000.5 + i * 0.5,
                low=1999.5 + i * 0.5,
                close=2000.0 + i * 0.5,
                source="test_fixture",
            )
            for i in range(200)
        ]
        await CandleRepository(setup_session).insert_new(candles)
        claim = BookClaim(
            book_id=uuid.uuid4(),
            chunk_id=uuid.uuid4(),
            statement="Market structure shifts precede continuation.",
            topic="market_structure",
        )
        setup_session.add(claim)
        await setup_session.commit()

    watcher = BooksFolderWatcher(
        watched_directory=tmp_path,
        embedding_provider=FakeEmbeddingProvider(dimension=8),
        qdrant_client=FakeQdrantClient(),  # type: ignore[arg-type]
        session_factory=_committing_session_factory(engine),
        interval_seconds=60,
        claim_validation_symbol_id=symbol.id,
    )

    result = await watcher.scan_once()

    assert len(result.claim_validations) == 1
    assert result.claim_validations[0].claim_id == claim.id

    async with raw_session_factory() as check_session:
        reloaded = await BookClaimRepository(check_session).get_by_id(claim.id)
    assert reloaded is not None
    assert reloaded.validation_status != "pending"


async def test_scan_once_skips_claim_validation_without_a_configured_symbol(
    engine: AsyncEngine, tmp_path: Path
) -> None:
    result = await _watcher(tmp_path, engine, FakeQdrantClient()).scan_once()

    assert result.claim_validations == []
