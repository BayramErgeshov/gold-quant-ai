"""Async Qdrant client factory.

Per DATABASE.md, Qdrant stores every semantic embedding collection (books,
research, news, historical, journal, market, strategies). This module owns
the single client instance; collection creation lives in `collections.py`.
"""

from __future__ import annotations

from functools import lru_cache

from qdrant_client import AsyncQdrantClient

from src.settings import get_settings


@lru_cache(maxsize=1)
def get_qdrant_client() -> AsyncQdrantClient:
    """Build (and cache) the process-wide async Qdrant client.

    Returns:
        A cached `AsyncQdrantClient` configured from `get_settings()`.
    """
    settings = get_settings()
    return AsyncQdrantClient(
        host=settings.qdrant.host,
        port=settings.qdrant.port,
        api_key=settings.qdrant.api_key.get_secret_value() or None,
    )
