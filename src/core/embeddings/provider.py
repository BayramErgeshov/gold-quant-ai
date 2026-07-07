"""Abstract base class every embedding provider implements.

Per BOOK_RAG.md ("Every chunk receives... Vector Embedding") and
CONFIGURATION.md ("Every configurable value must exist in configuration
files"): the embedding provider is selected entirely by
`config/books.yaml` (`embedding.provider`) — switching from local
sentence-transformers models to OpenAI (or any future provider) requires
no code changes, only configuration.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    """Base class for a text-to-vector embedding backend.

    Attributes:
        name: Human-readable provider name, e.g. "sentence-transformers".
    """

    name: str

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Vector dimension produced by this provider.

        Returns:
            The embedding vector size. Used to create/validate the Qdrant
            collection dimension at runtime (BOOK_RAG.md), since different
            models/providers produce differently-sized vectors.
        """

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts.

        Args:
            texts: Non-empty list of text chunks to embed.

        Returns:
            One embedding vector per input text, in the same order.

        Raises:
            src.core.data_collection.exceptions.ProviderError: If
                embedding fails (model unavailable, API error, ...).
        """
