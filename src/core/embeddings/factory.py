"""Embedding provider factory.

The single switch point for changing embedding backends: selects the
active `EmbeddingProvider` based on `config/books.yaml`
(`embedding.provider`). Adding a new provider means implementing
`EmbeddingProvider` and adding one branch here — no other code changes.
"""

from __future__ import annotations

from functools import lru_cache

from src.core.data_collection.exceptions import ProviderError
from src.core.embeddings.local_provider import LocalSentenceTransformerProvider
from src.core.embeddings.openai_provider import OpenAIEmbeddingProvider
from src.core.embeddings.provider import EmbeddingProvider
from src.settings import Settings, get_settings


def build_embedding_provider(settings: Settings) -> EmbeddingProvider:
    """Construct the embedding provider configured in `config/books.yaml`.

    Args:
        settings: Application settings.

    Returns:
        A new `EmbeddingProvider` instance matching `books.embedding.provider`.

    Raises:
        ProviderError: If `books.embedding.provider` is not a recognized value.
    """
    embedding_config = settings.platform.books.embedding

    if embedding_config.provider == "local":
        return LocalSentenceTransformerProvider(
            embedding_config.local.model_candidates,
            device=embedding_config.local.device,
        )
    if embedding_config.provider == "openai":
        return OpenAIEmbeddingProvider(
            model=embedding_config.openai.model,
            dimension=embedding_config.openai.dimension,
            api_key=settings.data_providers.openai_api_key.get_secret_value(),
        )

    raise ProviderError(f"Unknown embedding provider: {embedding_config.provider!r}")


@lru_cache(maxsize=1)
def get_embedding_provider() -> EmbeddingProvider:
    """Build (and cache) the process-wide embedding provider.

    Returns:
        The cached `EmbeddingProvider`, built from `get_settings()`.
    """
    return build_embedding_provider(get_settings())
