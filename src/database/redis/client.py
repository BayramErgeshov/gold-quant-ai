"""Async Redis client factory.

Per DATABASE.md, Redis holds queues, cache, temporary memory, sessions and
agent communication. This module owns the single connection pool; every
consumer (cache, queues, scheduler locks, ...) is built on top of it in the
phase that introduces it, rather than duplicating connection setup.
"""

from __future__ import annotations

from functools import lru_cache

import redis.asyncio as redis

from src.settings import get_settings


@lru_cache(maxsize=1)
def get_redis_client() -> redis.Redis:
    """Build (and cache) the process-wide async Redis client.

    Returns:
        A cached `redis.asyncio.Redis` client configured from `get_settings()`.
    """
    settings = get_settings()
    return redis.from_url(
        settings.redis.url,
        max_connections=settings.platform.database.redis.get("max_connections", 50),
        socket_timeout=settings.platform.database.redis.get("socket_timeout_seconds", 5),
        decode_responses=settings.platform.database.redis.get("decode_responses", True),
    )
