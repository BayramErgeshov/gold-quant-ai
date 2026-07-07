"""NewsAPI.org provider adapter.

Tier 2 news source per NEWS_ENGINE.md source tiering (Reuters/Bloomberg
direct feeds are Tier 1 but require enterprise contracts not yet
provisioned; NewsAPI aggregates many outlets and serves as an interim Tier
2 source). Requires `NEWSAPI_API_KEY`.
"""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.core.data_collection.exceptions import ProviderError
from src.core.data_collection.models import ProviderTier, SourceCategory
from src.core.data_collection.provider import DataProvider
from src.settings import Settings, get_settings

_BASE_URL = "https://newsapi.org/v2/everything"
_TIMEOUT_SECONDS = 10.0


class NewsApiProvider(DataProvider[list[dict[str, Any]]]):
    """Fetches news articles matching a query from NewsAPI.org."""

    name = "newsapi"
    category = SourceCategory.NEWS
    tier = ProviderTier.TIER_2
    reliability = 0.75

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    @property
    def is_configured(self) -> bool:
        return bool(self._settings.data_providers.newsapi_api_key.get_secret_value())

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, max=5),
        retry=retry_if_exception_type(httpx.TransportError),
    )
    async def _request(self, params: dict[str, Any]) -> httpx.Response:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.get(
                _BASE_URL,
                params=params,
                headers={
                    "X-Api-Key": self._settings.data_providers.newsapi_api_key.get_secret_value()
                },
            )
            response.raise_for_status()
            return response

    async def fetch(self, **kwargs: object) -> list[dict[str, Any]]:
        """Fetch articles matching a search query.

        Args:
            query: Search query, e.g. "gold OR XAUUSD".
            page_size: Maximum number of articles to return (default 20).

        Returns:
            A list of article dicts as returned by NewsAPI.

        Raises:
            ProviderError: If the request is malformed, the API responds
                with an error, or the network request fails after retries.
        """
        query = kwargs.get("query")
        if not isinstance(query, str):
            raise ProviderError("fetch() requires a 'query' string argument")
        page_size = kwargs.get("page_size", 20)

        params = {"q": query, "pageSize": page_size, "language": "en", "sortBy": "publishedAt"}

        try:
            response = await self._request(params)
        except httpx.HTTPStatusError as exc:
            raise ProviderError(f"NewsAPI returned HTTP {exc.response.status_code}") from exc
        except httpx.TransportError as exc:
            raise ProviderError(f"NewsAPI request failed after retries: {exc}") from exc

        payload = response.json()
        articles = payload.get("articles")
        if not isinstance(articles, list):
            raise ProviderError("NewsAPI response missing 'articles' array")
        return articles
