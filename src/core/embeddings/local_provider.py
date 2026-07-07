"""Local sentence-transformers embedding provider.

Per the project's embedding configuration (`config/books.yaml`
`embedding.local.model_candidates`), tries each candidate model in order and
uses the first one that loads successfully — by default BAAI/bge-m3, falling
back to BAAI/bge-large-en-v1.5, then the much smaller
all-MiniLM-L6-v2 if larger models cannot be downloaded or loaded (no
internet access, insufficient disk/memory). Runs entirely locally: no
external API calls, no API key required.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from typing import Any

from src.common.logging import get_logger
from src.core.data_collection.exceptions import ProviderError
from src.core.embeddings.provider import EmbeddingProvider

logger = get_logger(__name__)

# (model_name: str, *, device: str) -> object exposing `.encode()` and
# `.get_sentence_embedding_dimension()` (i.e. a `SentenceTransformer`-shaped
# object). Injectable so tests never need to download a real model.
ModelFactory = Callable[..., Any]


def _default_model_factory(model_name: str, *, device: str) -> Any:  # pragma: no cover
    """Load a real `SentenceTransformer` model. The default `ModelFactory`.

    Not unit-tested directly (would require downloading real model
    weights); covered by injecting a fake factory in tests instead.
    """
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name, device=device)


class LocalSentenceTransformerProvider(EmbeddingProvider):
    """Embeds text locally via sentence-transformers, with model fallback."""

    name = "sentence-transformers"

    def __init__(
        self,
        model_candidates: Sequence[str],
        *,
        device: str = "cpu",
        model_factory: ModelFactory | None = None,
    ) -> None:
        """Initialize the provider.

        Args:
            model_candidates: Model names tried in order, first success wins.
            device: torch device to load the model onto, e.g. "cpu", "cuda".
            model_factory: Injectable model loader, defaults to loading a
                real `SentenceTransformer`. Tests inject a fake factory to
                avoid downloading multi-gigabyte model weights.

        Raises:
            ValueError: If `model_candidates` is empty.
        """
        if not model_candidates:
            raise ValueError("model_candidates must not be empty")
        self._model_candidates = list(model_candidates)
        self._device = device
        self._model_factory = model_factory or _default_model_factory
        self._model: Any | None = None
        self._loaded_model_name: str | None = None

    @property
    def loaded_model_name(self) -> str | None:
        """The model actually loaded, or None if no `embed`/`dimension` call has run yet."""
        return self._loaded_model_name

    def _ensure_model_loaded(self) -> Any:
        """Load the first candidate model that succeeds, caching the result."""
        if self._model is not None:
            return self._model

        errors: list[str] = []
        for model_name in self._model_candidates:
            try:
                self._model = self._model_factory(model_name, device=self._device)
            except Exception as exc:  # noqa: BLE001 - try the next candidate on any failure
                errors.append(f"{model_name}: {exc}")
                logger.warning("embedding_model_load_failed", model=model_name, error=str(exc))
                continue
            self._loaded_model_name = model_name
            logger.info("embedding_model_loaded", model=model_name, device=self._device)
            return self._model

        raise ProviderError(f"No local embedding model could be loaded. Tried: {'; '.join(errors)}")

    @property
    def dimension(self) -> int:
        model = self._ensure_model_loaded()
        return int(model.get_sentence_embedding_dimension())

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed texts in a worker thread (model load + inference are CPU-bound)."""
        if not texts:
            raise ProviderError("embed() requires a non-empty list of texts")

        def _encode() -> list[list[float]]:
            model = self._ensure_model_loaded()
            vectors = model.encode(texts, convert_to_numpy=True)
            return [vector.tolist() for vector in vectors]

        return await asyncio.to_thread(_encode)
