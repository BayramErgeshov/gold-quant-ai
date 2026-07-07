"""Redis-backed cache for the Data Collection Engine fallback chain.

Per DATA_COLLECTION_ENGINE.md fallback order: "Tier 1 -> Tier 2 -> Tier 3 ->
Cached Data -> Historical Model." This module is the "Cached Data" step —
a last-known-good value served when every live provider is unavailable.
"""

from __future__ import annotations

import json
from typing import Any

from src.database.redis.client import get_redis_client

_KEY_PREFIX = "data_collection"
_DEFAULT_TTL_SECONDS = 6 * 60 * 60  # 6 hours: stale-but-usable per FAILSAFE_PROTOCOL.md


def build_cache_key(category: str, provider_query: str) -> str:
    """Build a namespaced Redis key for a given category/query pair.

    Args:
        category: Data category, e.g. "economic_data".
        provider_query: A stable string identifying the specific query,
            e.g. "fred:CPIAUCSL".

    Returns:
        A namespaced cache key.
    """
    return f"{_KEY_PREFIX}:{category}:{provider_query}"


async def get_cached(key: str) -> Any | None:
    """Fetch a previously cached, JSON-serialized value.

    Args:
        key: Cache key built via `build_cache_key`.

    Returns:
        The deserialized value, or None if not present.
    """
    client = get_redis_client()
    raw = await client.get(key)
    return json.loads(raw) if raw is not None else None


async def set_cached(key: str, value: Any, *, ttl_seconds: int = _DEFAULT_TTL_SECONDS) -> None:
    """Store a JSON-serializable value under the given cache key.

    Args:
        key: Cache key built via `build_cache_key`.
        value: A JSON-serializable value to cache.
        ttl_seconds: Time-to-live before the cached value expires.
    """
    client = get_redis_client()
    await client.set(key, json.dumps(value), ex=ttl_seconds)
