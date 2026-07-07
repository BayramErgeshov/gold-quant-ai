"""Unit tests for `src.database.qdrant.client`."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.database.qdrant.client import get_qdrant_client

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    get_qdrant_client.cache_clear()
    yield
    get_qdrant_client.cache_clear()


def test_get_qdrant_client_is_cached() -> None:
    assert get_qdrant_client() is get_qdrant_client()


def test_get_qdrant_client_uses_settings_host_and_port() -> None:
    with patch(
        "src.database.qdrant.client.AsyncQdrantClient", MagicMock()
    ) as mock_client_class:
        get_qdrant_client()

    mock_client_class.assert_called_once_with(host="localhost", port=6333, api_key=None)
