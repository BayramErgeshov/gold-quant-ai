"""Unit tests for `src.core.embeddings.factory`."""

from __future__ import annotations

import pytest

from src.core.data_collection.exceptions import ProviderError
from src.core.embeddings.factory import build_embedding_provider, get_embedding_provider
from src.core.embeddings.local_provider import LocalSentenceTransformerProvider
from src.core.embeddings.openai_provider import OpenAIEmbeddingProvider
from src.settings import get_settings

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    get_embedding_provider.cache_clear()
    yield
    get_embedding_provider.cache_clear()


def test_builds_local_provider_by_default() -> None:
    provider = build_embedding_provider(get_settings())

    assert isinstance(provider, LocalSentenceTransformerProvider)


def test_builds_openai_provider_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    settings.platform.books.embedding.provider = "openai"

    provider = build_embedding_provider(settings)

    assert isinstance(provider, OpenAIEmbeddingProvider)
    assert provider.dimension == settings.platform.books.embedding.openai.dimension


def test_raises_for_unknown_provider() -> None:
    settings = get_settings()
    settings.platform.books.embedding.provider = "unknown"  # type: ignore[assignment]

    with pytest.raises(ProviderError, match="Unknown embedding provider"):
        build_embedding_provider(settings)


def test_get_embedding_provider_is_cached() -> None:
    assert get_embedding_provider() is get_embedding_provider()
