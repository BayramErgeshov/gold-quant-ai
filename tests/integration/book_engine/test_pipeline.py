"""Integration tests for `BookIngestionPipeline`.

Exercises the real pipeline against a real (in-memory SQLite) database and
an in-memory fake Qdrant client, mocking only the PDF text extraction step
(which requires a well-formed PDF file) so chunking, embedding, topic
classification, entity extraction, persistence and knowledge graph updates
all run for real.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from sqlalchemy.ext.asyncio import AsyncSession

from src.engines.book_engine.pipeline import BOOKS_COLLECTION_NAME, BookIngestionPipeline
from src.engines.book_engine.text_extraction import ExtractedPage
from src.repositories.book_chunk_repository import BookChunkRepository
from src.repositories.book_claim_repository import BookClaimRepository
from src.repositories.book_repository import BookRepository
from src.repositories.concept_repository import ConceptRelationshipRepository, ConceptRepository
from tests.integration.book_engine._fakes import FakeEmbeddingProvider, FakeQdrantClient

_SMART_MONEY_TEXT = (
    "Institutional smart money frequently leaves an order block before a "
    "strong displacement move. Liquidity above equal highs is often swept "
    "before the reversal, confirming a change of character in market structure."
)


def _build_pipeline(session: AsyncSession, qdrant: FakeQdrantClient) -> BookIngestionPipeline:
    return BookIngestionPipeline(
        book_repository=BookRepository(session),
        chunk_repository=BookChunkRepository(session),
        claim_repository=BookClaimRepository(session),
        concept_repository=ConceptRepository(session),
        concept_relationship_repository=ConceptRelationshipRepository(session),
        embedding_provider=FakeEmbeddingProvider(dimension=8),
        qdrant_client=qdrant,  # type: ignore[arg-type]
    )


async def test_ingest_creates_book_chunks_and_qdrant_points(
    session: AsyncSession, tmp_path: Path
) -> None:
    qdrant = FakeQdrantClient()
    pipeline = _build_pipeline(session, qdrant)
    pdf_path = tmp_path / "smart_money.pdf"
    pdf_path.write_bytes(b"irrelevant, extract_pages is mocked")

    with patch(
        "src.engines.book_engine.pipeline.extract_document_pages",
        return_value=[ExtractedPage(page_number=1, text=_SMART_MONEY_TEXT, used_ocr=False)],
    ):
        book = await pipeline.ingest(pdf_path, title="Smart Money Concepts", author="Author X")

    assert book.title == "Smart Money Concepts"
    assert book.pages == 1
    assert book.language == "en"

    chunks = await BookChunkRepository(session).list_by_book(book.id)
    assert len(chunks) == 1
    assert chunks[0].topic == "smart_money"
    assert chunks[0].confidence > 0

    collection = qdrant.collections[BOOKS_COLLECTION_NAME]
    assert collection.size == 8
    assert len(collection.points) == 1

    claims = await BookClaimRepository(session).list_all()
    assert len(claims) > 0
    assert all(claim.book_id == book.id for claim in claims)
    assert all(claim.chunk_id == chunks[0].id for claim in claims)
    assert all(claim.topic == "smart_money" for claim in claims)
    assert all(claim.validation_status == "pending" for claim in claims)


async def test_ingest_is_idempotent_for_same_source_path(
    session: AsyncSession, tmp_path: Path
) -> None:
    qdrant = FakeQdrantClient()
    pipeline = _build_pipeline(session, qdrant)
    pdf_path = tmp_path / "book.pdf"
    pdf_path.write_bytes(b"irrelevant")

    with patch(
        "src.engines.book_engine.pipeline.extract_document_pages",
        return_value=[ExtractedPage(page_number=1, text=_SMART_MONEY_TEXT, used_ocr=False)],
    ):
        first = await pipeline.ingest(pdf_path, title="Book", author="Author")
        second = await pipeline.ingest(pdf_path, title="Book", author="Author")

    assert first.id == second.id
    all_books = await BookRepository(session).list_all()
    assert len(all_books) == 1


async def test_ingest_creates_knowledge_graph_relationships_for_co_occurring_topics(
    session: AsyncSession, tmp_path: Path
) -> None:
    qdrant = FakeQdrantClient()
    pipeline = _build_pipeline(session, qdrant)
    pdf_path = tmp_path / "book.pdf"
    pdf_path.write_bytes(b"irrelevant")

    with patch(
        "src.engines.book_engine.pipeline.extract_document_pages",
        return_value=[ExtractedPage(page_number=1, text=_SMART_MONEY_TEXT, used_ocr=False)],
    ):
        await pipeline.ingest(pdf_path, title="Book", author="Author")

    concepts = ConceptRepository(session)
    smart_money = await concepts.get_by_name("smart_money")
    assert smart_money is not None
    relationships = await ConceptRelationshipRepository(session).list_related(smart_money.id)
    assert len(relationships) > 0


async def test_ingest_registers_single_concept_when_only_one_topic_matches(
    session: AsyncSession, tmp_path: Path
) -> None:
    qdrant = FakeQdrantClient()
    pipeline = _build_pipeline(session, qdrant)
    pdf_path = tmp_path / "gold_only.pdf"
    pdf_path.write_bytes(b"irrelevant")

    with patch(
        "src.engines.book_engine.pipeline.extract_document_pages",
        return_value=[
            ExtractedPage(page_number=1, text="This chapter is only about gold.", used_ocr=False)
        ],
    ):
        book = await pipeline.ingest(pdf_path, title="Gold Only", author="Author")

    concepts = ConceptRepository(session)
    gold_concept = await concepts.get_by_name("gold")
    assert gold_concept is not None
    relationships = await ConceptRelationshipRepository(session).list_related(gold_concept.id)
    assert relationships == []

    chunks = await BookChunkRepository(session).list_by_book(book.id)
    assert chunks[0].topic == "gold"


async def test_ingest_skips_book_with_no_extractable_text(
    session: AsyncSession, tmp_path: Path
) -> None:
    qdrant = FakeQdrantClient()
    pipeline = _build_pipeline(session, qdrant)
    pdf_path = tmp_path / "blank.pdf"
    pdf_path.write_bytes(b"irrelevant")

    with patch(
        "src.engines.book_engine.pipeline.extract_document_pages",
        return_value=[ExtractedPage(page_number=1, text="", used_ocr=False)],
    ):
        book = await pipeline.ingest(pdf_path, title="Blank", author="Nobody")

    chunks = await BookChunkRepository(session).list_by_book(book.id)
    assert chunks == []
