"""Book ingestion pipeline orchestrator.

Runs the full BOOK_RAG.md pipeline for a single document:

    Import -> OCR if needed -> Language Detection -> Cleaning -> Chunking ->
    Embedding -> Topic Classification -> Entity Recognition ->
    Knowledge Graph Update -> Qdrant Storage -> Validation Queue

Claim extraction/validation is intentionally out of scope for automatic
ingestion: BOOK_RAG.md requires every claim to pass historical validation
before becoming "production knowledge", which needs the Historical
Research Engine (a later roadmap phase). This pipeline persists chunks and
concepts only; claims are added explicitly via `BookClaimRepository` once
that validation capability exists.
"""

from __future__ import annotations

from itertools import combinations
from pathlib import Path

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import PointStruct

from src.common.logging import get_logger
from src.core.embeddings.provider import EmbeddingProvider
from src.database.qdrant.collections import ensure_collection_for_dimension
from src.engines.book_engine.chunking import chunk_page_text
from src.engines.book_engine.cleaning import clean_text
from src.engines.book_engine.entity_extraction import extract_entities
from src.engines.book_engine.language_detection import detect_language
from src.engines.book_engine.text_extraction import extract_pages
from src.engines.book_engine.topic_classification import classify_topics
from src.models.book import Book, BookChunk
from src.repositories.book_chunk_repository import BookChunkRepository
from src.repositories.book_repository import BookRepository
from src.repositories.concept_repository import ConceptRelationshipRepository, ConceptRepository

logger = get_logger(__name__)

BOOKS_COLLECTION_NAME = "books"
_TOPICS_PER_CHUNK = 3
_CO_OCCURRENCE_RELATIONSHIP = "co_occurs_with"


class BookIngestionPipeline:
    """Orchestrates ingestion of a single book/document end-to-end."""

    def __init__(
        self,
        *,
        book_repository: BookRepository,
        chunk_repository: BookChunkRepository,
        concept_repository: ConceptRepository,
        concept_relationship_repository: ConceptRelationshipRepository,
        embedding_provider: EmbeddingProvider,
        qdrant_client: AsyncQdrantClient,
    ) -> None:
        """Initialize the pipeline with its collaborators (constructor injection).

        Args:
            book_repository: Persists `Book` rows.
            chunk_repository: Persists `BookChunk` rows.
            concept_repository: Persists knowledge graph concept nodes.
            concept_relationship_repository: Persists knowledge graph edges.
            embedding_provider: Active embedding backend (BOOK_RAG.md /
                `config/books.yaml` `embedding.provider`).
            qdrant_client: Active Qdrant client for vector storage.
        """
        self._books = book_repository
        self._chunks = chunk_repository
        self._concepts = concept_repository
        self._concept_relationships = concept_relationship_repository
        self._embedding_provider = embedding_provider
        self._qdrant = qdrant_client

    async def ingest(
        self,
        pdf_path: Path,
        *,
        title: str,
        author: str,
        edition: str | None = None,
        publisher: str | None = None,
    ) -> Book:
        """Ingest a single PDF book end-to-end.

        Args:
            pdf_path: Path to the PDF file (typically under `books/uploaded/`).
            title: Book title.
            author: Author name(s).
            edition: Edition string, if known.
            publisher: Publisher name, if known.

        Returns:
            The persisted `Book`. If a book with the same `source_path` was
            already ingested, that existing `Book` is returned unchanged
            (BOOK_RAG.md: "Whenever a new book arrives... Do not rebuild
            the database").
        """
        existing = await self._books.get_by_source_path(str(pdf_path))
        if existing is not None:
            logger.info("book_already_ingested", source_path=str(pdf_path))
            return existing

        await ensure_collection_for_dimension(
            self._qdrant, BOOKS_COLLECTION_NAME, dimension=self._embedding_provider.dimension
        )

        pages = extract_pages(pdf_path)
        cleaned_pages = [(page.page_number, clean_text(page.text)) for page in pages]
        language_sample = " ".join(text for _, text in cleaned_pages[:3])

        book = await self._books.add(
            Book(
                title=title,
                author=author,
                edition=edition,
                publisher=publisher,
                language=detect_language(language_sample),
                source_path=str(pdf_path),
                pages=len(pages),
            )
        )

        text_chunks = [
            chunk
            for page_number, text in cleaned_pages
            if text
            for chunk in chunk_page_text(text, page=page_number)
        ]
        if not text_chunks:
            logger.warning("book_produced_no_chunks", source_path=str(pdf_path))
            return book

        embeddings = await self._embedding_provider.embed([chunk.text for chunk in text_chunks])
        points: list[PointStruct] = []

        for chunk, vector in zip(text_chunks, embeddings, strict=True):
            topic_scores = classify_topics(chunk.text, max_topics=_TOPICS_PER_CHUNK)
            topics = [score.topic for score in topic_scores]
            primary_topic = topics[0] if topics else None
            confidence = topic_scores[0].score if topic_scores else 0.0
            entities = extract_entities(chunk.text)

            stored_chunk = await self._chunks.add(
                BookChunk(
                    book_id=book.id,
                    page=chunk.page,
                    text=chunk.text,
                    topic=primary_topic,
                    entities=entities,
                    confidence=confidence,
                )
            )
            points.append(
                PointStruct(
                    id=str(stored_chunk.id),
                    vector=vector,
                    payload={
                        "book_id": str(book.id),
                        "page": chunk.page,
                        "topic": primary_topic,
                        "title": title,
                        "author": author,
                    },
                )
            )

            await self._update_knowledge_graph(topics)

        await self._qdrant.upsert(collection_name=BOOKS_COLLECTION_NAME, points=points)

        logger.info(
            "book_ingested",
            source_path=str(pdf_path),
            chunk_count=len(text_chunks),
            book_id=str(book.id),
        )
        return book

    async def _update_knowledge_graph(self, topics: list[str]) -> None:
        """Register co-occurring topics as linked concepts (BOOK_RAG.md Knowledge Graph)."""
        if len(topics) < 2:
            for topic in topics:
                await self._concepts.get_or_create(topic, category=topic)
            return

        concepts = {
            topic: await self._concepts.get_or_create(topic, category=topic) for topic in topics
        }
        for topic_a, topic_b in combinations(topics, 2):
            await self._concept_relationships.link(
                concepts[topic_a].id,
                concepts[topic_b].id,
                relationship_type=_CO_OCCURRENCE_RELATIONSHIP,
            )
