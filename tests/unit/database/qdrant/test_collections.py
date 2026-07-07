"""Unit tests for `src.database.qdrant.collections`."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from qdrant_client.models import Distance, HnswConfigDiff

from src.database.qdrant.collections import (
    CollectionDimensionMismatchError,
    ensure_collection_for_dimension,
    ensure_collections_exist,
)
from src.settings import get_settings

pytestmark = pytest.mark.unit


def _existing_collections_response(names: list[str]) -> MagicMock:
    response = MagicMock()
    response.collections = [MagicMock(name=name) for name in names]
    for mock_collection, name in zip(response.collections, names, strict=True):
        mock_collection.name = name
    return response


async def test_creates_all_missing_collections() -> None:
    client = AsyncMock()
    client.get_collections.return_value = _existing_collections_response([])

    created = await ensure_collections_exist(client, get_settings())

    expected = set(get_settings().platform.database.qdrant["collections"].keys())
    assert set(created) == expected
    assert client.create_collection.await_count == len(expected)
    _, kwargs = client.create_collection.await_args
    assert kwargs["hnsw_config"].m == 16
    assert kwargs["hnsw_config"].ef_construct == 200


async def test_skips_collections_that_already_exist() -> None:
    client = AsyncMock()
    client.get_collections.return_value = _existing_collections_response(["research", "news"])

    created = await ensure_collections_exist(client, get_settings())

    total_configured = len(get_settings().platform.database.qdrant["collections"])
    assert "research" not in created
    assert "news" not in created
    assert len(created) == total_configured - 2
    assert client.create_collection.await_count == total_configured - 2


async def test_ensure_collection_for_dimension_creates_when_missing() -> None:
    client = AsyncMock()
    client.get_collections.return_value = _existing_collections_response([])

    created = await ensure_collection_for_dimension(client, "books", dimension=1024)

    assert created is True
    client.create_collection.assert_awaited_once()
    _, kwargs = client.create_collection.await_args
    assert kwargs["vectors_config"].size == 1024
    assert kwargs["vectors_config"].distance == Distance.COSINE
    assert kwargs["hnsw_config"].m == 16
    assert kwargs["hnsw_config"].ef_construct == 200


async def test_ensure_collection_for_dimension_accepts_custom_hnsw_config() -> None:
    client = AsyncMock()
    client.get_collections.return_value = _existing_collections_response([])
    custom_config = HnswConfigDiff(m=32, ef_construct=400)

    await ensure_collection_for_dimension(
        client, "books", dimension=1024, hnsw_config=custom_config
    )

    _, kwargs = client.create_collection.await_args
    assert kwargs["hnsw_config"] is custom_config


async def test_ensure_collection_for_dimension_noop_when_matching() -> None:
    client = AsyncMock()
    client.get_collections.return_value = _existing_collections_response(["books"])
    collection_info = MagicMock()
    collection_info.config.params.vectors.size = 1024
    client.get_collection.return_value = collection_info

    created = await ensure_collection_for_dimension(client, "books", dimension=1024)

    assert created is False
    client.create_collection.assert_not_awaited()


async def test_ensure_collection_for_dimension_raises_on_mismatch() -> None:
    client = AsyncMock()
    client.get_collections.return_value = _existing_collections_response(["books"])
    collection_info = MagicMock()
    collection_info.config.params.vectors.size = 384
    client.get_collection.return_value = collection_info

    with pytest.raises(CollectionDimensionMismatchError, match="384"):
        await ensure_collection_for_dimension(client, "books", dimension=1024)
