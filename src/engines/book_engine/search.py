"""Semantic search over ingested books (BOOK_RAG.md: "RAG Retrieval").

Per BOOK_RAG.md: "Whenever another agent asks... Retrieve Most Relevant
Chunks... Never answer from memory if retrieval is available." This is
the retrieval half of RAG; answer synthesis belongs to the Chief AI /
research departments that consume these results in later roadmap phases.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from qdrant_client import AsyncQdrantClient

from src.core.embeddings.provider import EmbeddingProvider
from src.engines.book_engine.pipeline import BOOKS_COLLECTION_NAME
from src.repositories.book_chunk_repository import BookChunkRepository


@dataclass(frozen=True, slots=True)
class SearchResult:
    """A single retrieved book chunk, ranked by semantic similarity.

    Attributes:
        chunk_id: The matched `BookChunk` id.
        book_id: The owning `Book` id, from the Qdrant point payload.
        text: The chunk's text content, if still present in Postgres.
        topic: The chunk's classified topic, if known.
        score: Similarity score reported by Qdrant (higher is more similar).
    """

    chunk_id: str
    book_id: str
    text: str | None
    topic: str | None
    score: float


class BookSemanticSearch:
    """Retrieves the most relevant book chunks for a natural-language query."""

    def __init__(
        self,
        *,
        qdrant_client: AsyncQdrantClient,
        embedding_provider: EmbeddingProvider,
        chunk_repository: BookChunkRepository,
    ) -> None:
        """Initialize the search service (constructor injection).

        Args:
            qdrant_client: Active Qdrant client to query the books collection.
            embedding_provider: Active embedding backend, used to embed the query.
            chunk_repository: Used to fetch full chunk text and record usage.
        """
        self._qdrant = qdrant_client
        self._embedding_provider = embedding_provider
        self._chunks = chunk_repository

    async def search(self, query: str, *, limit: int = 5) -> list[SearchResult]:
        """Search ingested books for chunks relevant to a query.

        Args:
            query: Natural-language question or topic.
            limit: Maximum number of results to return.

        Returns:
            Up to `limit` `SearchResult`, most relevant first. Every
            returned chunk's usage count is incremented
            (BOOK_RAG.md "Learning: Was it referenced").
        """
        (vector,) = await self._embedding_provider.embed([query])
        response = await self._qdrant.query_points(
            collection_name=BOOKS_COLLECTION_NAME, query=vector, limit=limit
        )

        results: list[SearchResult] = []
        for point in response.points:
            chunk_id = uuid.UUID(str(point.id))
            await self._chunks.increment_usage(chunk_id)
            chunk = await self._chunks.get_by_id(chunk_id)
            payload = point.payload or {}
            results.append(
                SearchResult(
                    chunk_id=str(point.id),
                    book_id=str(payload.get("book_id", "")),
                    text=chunk.text if chunk is not None else None,
                    topic=chunk.topic if chunk is not None else None,
                    score=point.score,
                )
            )

        return results
