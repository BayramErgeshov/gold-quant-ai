"""Integration tests for `BookSemanticSearch`."""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import patch

from sqlalchemy.ext.asyncio import AsyncSession

from src.engines.book_engine.pipeline import BookIngestionPipeline
from src.engines.book_engine.search import BookSemanticSearch
from src.engines.book_engine.text_extraction import ExtractedPage
from src.repositories.book_chunk_repository import BookChunkRepository
from src.repositories.book_claim_repository import BookClaimRepository
from src.repositories.book_repository import BookRepository
from src.repositories.concept_repository import ConceptRelationshipRepository, ConceptRepository
from tests.integration.book_engine._fakes import (
    FakeCollection,
    FakeEmbeddingProvider,
    FakeQdrantClient,
)

_TEXT = (
    "Institutional smart money frequently leaves an order block before a "
    "strong displacement move in market structure."
)


async def _ingest_one_book(session: AsyncSession, qdrant: FakeQdrantClient) -> None:
    pipeline = BookIngestionPipeline(
        book_repository=BookRepository(session),
        chunk_repository=BookChunkRepository(session),
        claim_repository=BookClaimRepository(session),
        concept_repository=ConceptRepository(session),
        concept_relationship_repository=ConceptRelationshipRepository(session),
        embedding_provider=FakeEmbeddingProvider(dimension=8),
        qdrant_client=qdrant,  # type: ignore[arg-type]
    )
    with patch(
        "src.engines.book_engine.pipeline.extract_document_pages",
        return_value=[ExtractedPage(page_number=1, text=_TEXT, used_ocr=False)],
    ):
        await pipeline.ingest(Path("book.pdf"), title="Book", author="Author")


async def test_search_returns_results_and_increments_usage(session: AsyncSession) -> None:
    qdrant = FakeQdrantClient()
    await _ingest_one_book(session, qdrant)

    search = BookSemanticSearch(
        qdrant_client=qdrant,  # type: ignore[arg-type]
        embedding_provider=FakeEmbeddingProvider(dimension=8),
        chunk_repository=BookChunkRepository(session),
    )

    results = await search.search("order block liquidity", limit=5)

    assert len(results) == 1
    assert results[0].topic == "smart_money"
    assert results[0].text is not None

    chunk = await BookChunkRepository(session).get_by_id(uuid.UUID(results[0].chunk_id))
    assert chunk is not None
    assert chunk.usage_count == 1


async def test_search_returns_empty_list_for_empty_collection(session: AsyncSession) -> None:
    qdrant = FakeQdrantClient()
    qdrant.collections["books"] = FakeCollection(size=8)

    search = BookSemanticSearch(
        qdrant_client=qdrant,  # type: ignore[arg-type]
        embedding_provider=FakeEmbeddingProvider(dimension=8),
        chunk_repository=BookChunkRepository(session),
    )

    results = await search.search("anything", limit=5)

    assert results == []
