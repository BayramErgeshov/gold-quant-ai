"""Shared test doubles for Book Engine pipeline/search tests.

An in-memory fake Qdrant client and a deterministic fake embedding
provider, so pipeline/search tests exercise real control flow (DB writes,
knowledge graph updates, vector upsert/query argument shapes) without
requiring a running Qdrant instance or a real embedding model.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock

from src.core.embeddings.provider import EmbeddingProvider


class FakeEmbeddingProvider(EmbeddingProvider):
    """Deterministic embedding provider: each text maps to a hash-based vector."""

    name = "fake"

    def __init__(self, dimension: int = 8) -> None:
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector_for(text) for text in texts]

    def _vector_for(self, text: str) -> list[float]:
        seed = sum(ord(character) for character in text) or 1
        return [math.sin(seed * (index + 1)) for index in range(self._dimension)]


@dataclass
class FakeCollection:
    size: int
    points: dict[str, tuple[list[float], dict[str, Any]]] = field(default_factory=dict)


class FakeQdrantClient:
    """In-memory stand-in for `AsyncQdrantClient` covering the calls Book Engine makes."""

    def __init__(self) -> None:
        self.collections: dict[str, FakeCollection] = {}

    async def get_collections(self) -> MagicMock:
        response = MagicMock()
        response.collections = []
        for name in self.collections:
            entry = MagicMock()
            entry.name = name
            response.collections.append(entry)
        return response

    async def create_collection(
        self, collection_name: str, vectors_config: Any, **kwargs: Any
    ) -> None:
        self.collections[collection_name] = FakeCollection(size=vectors_config.size)

    async def get_collection(self, collection_name: str) -> MagicMock:
        info = MagicMock()
        info.config.params.vectors.size = self.collections[collection_name].size
        return info

    async def upsert(self, collection_name: str, points: list[Any]) -> None:
        collection = self.collections[collection_name]
        for point in points:
            collection.points[str(point.id)] = (point.vector, point.payload)

    async def query_points(self, collection_name: str, query: list[float], limit: int) -> MagicMock:
        collection = self.collections[collection_name]

        def _score(vector: list[float]) -> float:
            return sum(a * b for a, b in zip(query, vector, strict=True))

        ranked = sorted(
            collection.points.items(), key=lambda item: _score(item[1][0]), reverse=True
        )

        response = MagicMock()
        response.points = []
        for point_id, (vector, payload) in ranked[:limit]:
            scored = MagicMock()
            scored.id = point_id
            scored.payload = payload
            scored.score = _score(vector)
            response.points.append(scored)
        return response
