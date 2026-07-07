"""Unit tests for `LocalSentenceTransformerProvider`.

Uses a fake model factory throughout — never downloads a real
sentence-transformers model in tests.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from src.core.data_collection.exceptions import ProviderError
from src.core.embeddings.local_provider import LocalSentenceTransformerProvider

pytestmark = pytest.mark.unit


class _FakeModel:
    def __init__(self, dimension: int) -> None:
        self._dimension = dimension

    def get_sentence_embedding_dimension(self) -> int:
        return self._dimension

    def encode(self, texts: list[str], *, convert_to_numpy: bool = True) -> list[MagicMock]:
        vectors = []
        for _ in texts:
            vector = MagicMock()
            vector.tolist.return_value = [0.1] * self._dimension
            vectors.append(vector)
        return vectors


def test_raises_on_empty_model_candidates() -> None:
    with pytest.raises(ValueError, match="model_candidates"):
        LocalSentenceTransformerProvider([])


def test_loads_first_candidate_when_available() -> None:
    factory = MagicMock(side_effect=lambda name, device: _FakeModel(1024))
    provider = LocalSentenceTransformerProvider(
        ["BAAI/bge-m3", "sentence-transformers/all-MiniLM-L6-v2"], model_factory=factory
    )

    assert provider.dimension == 1024
    assert provider.loaded_model_name == "BAAI/bge-m3"
    factory.assert_called_once_with("BAAI/bge-m3", device="cpu")


def test_falls_back_to_next_candidate_on_load_failure() -> None:
    def factory(name: str, *, device: str) -> Any:
        if name == "BAAI/bge-m3":
            raise OSError("no internet access")
        return _FakeModel(384)

    provider = LocalSentenceTransformerProvider(
        ["BAAI/bge-m3", "sentence-transformers/all-MiniLM-L6-v2"], model_factory=factory
    )

    assert provider.dimension == 384
    assert provider.loaded_model_name == "sentence-transformers/all-MiniLM-L6-v2"


def test_model_is_loaded_only_once() -> None:
    factory = MagicMock(side_effect=lambda name, device: _FakeModel(1024))
    provider = LocalSentenceTransformerProvider(["BAAI/bge-m3"], model_factory=factory)

    _ = provider.dimension
    _ = provider.dimension

    factory.assert_called_once()


def test_raises_provider_error_when_every_candidate_fails() -> None:
    def factory(name: str, *, device: str) -> Any:
        raise OSError(f"cannot load {name}")

    provider = LocalSentenceTransformerProvider(["model-a", "model-b"], model_factory=factory)

    with pytest.raises(ProviderError, match="No local embedding model could be loaded"):
        _ = provider.dimension


async def test_embed_returns_one_vector_per_text() -> None:
    factory = MagicMock(side_effect=lambda name, device: _FakeModel(384))
    provider = LocalSentenceTransformerProvider(["model-a"], model_factory=factory)

    vectors = await provider.embed(["hello", "world"])

    assert len(vectors) == 2
    assert all(len(vector) == 384 for vector in vectors)


async def test_embed_raises_on_empty_input() -> None:
    provider = LocalSentenceTransformerProvider(["model-a"], model_factory=MagicMock())

    with pytest.raises(ProviderError, match="non-empty"):
        await provider.embed([])
