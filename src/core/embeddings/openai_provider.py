"""OpenAI embedding provider adapter.

Alternative to the default local provider (`local_provider.py`), selected
via `config/books.yaml` (`embedding.provider: openai`). Requires
`OPENAI_API_KEY`. Implemented as a direct REST call rather than depending
on the `openai` SDK, per CODING_STANDARDS.md dependency policy ("evaluate
necessity... avoid unnecessary packages") — the embeddings endpoint is a
single simple POST request.
"""

from __future__ import annotations

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.core.data_collection.exceptions import ProviderError
from src.core.embeddings.provider import EmbeddingProvider

_BASE_URL = "https://api.openai.com/v1/embeddings"
_TIMEOUT_SECONDS = 30.0


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """Embeds text via the OpenAI embeddings API."""

    name = "openai"

    def __init__(self, *, model: str, dimension: int, api_key: str) -> None:
        """Initialize the provider.

        Args:
            model: OpenAI embedding model name, e.g. "text-embedding-3-large".
            dimension: Expected output vector dimension for `model`
                (from `config/books.yaml`, since the API does not report it).
            api_key: OpenAI API key. May be empty; `embed` then raises
                `ProviderError` rather than making an unauthenticated call.
        """
        self._model = model
        self._dimension = dimension
        self._api_key = api_key

    @property
    def dimension(self) -> int:
        return self._dimension

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, max=10),
        retry=retry_if_exception_type(httpx.TransportError),
    )
    async def _request(self, texts: list[str]) -> httpx.Response:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.post(
                _BASE_URL,
                json={"model": self._model, "input": texts},
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
            response.raise_for_status()
            return response

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts via the OpenAI API.

        Args:
            texts: Non-empty list of text chunks to embed.

        Returns:
            One embedding vector per input text, in the same order.

        Raises:
            ProviderError: If no API key is configured, the request is
                malformed, the API returns an error, or the network
                request fails after retries.
        """
        if not texts:
            raise ProviderError("embed() requires a non-empty list of texts")
        if not self._api_key:
            raise ProviderError("OpenAI embedding provider requires OPENAI_API_KEY")

        try:
            response = await self._request(texts)
        except httpx.HTTPStatusError as exc:
            raise ProviderError(
                f"OpenAI embeddings API returned HTTP {exc.response.status_code}"
            ) from exc
        except httpx.TransportError as exc:
            raise ProviderError(f"OpenAI embeddings request failed after retries: {exc}") from exc

        payload = response.json()
        data = payload.get("data")
        if not isinstance(data, list):
            raise ProviderError("OpenAI embeddings response missing 'data' array")
        return [item["embedding"] for item in data]
