"""Shared pytest fixtures for GOLD QUANT AI.

Per TESTING_STRATEGY.md, the test suite always runs against the isolated
`testing` environment profile (`config/testing.yaml`) — never development,
demo or production configuration.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

os.environ.setdefault("GOLD_ENVIRONMENT", "testing")


@pytest.fixture(autouse=True)
def _reset_settings_cache() -> Iterator[None]:
    """Ensure `get_settings()` is re-evaluated fresh for every test.

    Settings are cached process-wide via `lru_cache`; tests that mutate
    environment variables must not leak state into other tests.
    """
    from src.settings import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
