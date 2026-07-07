"""Unit tests for `src.telemetry.server`."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.telemetry import server as metrics_server
from src.telemetry.server import start_metrics_server

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _reset_started_flag() -> None:
    metrics_server._started = False


def test_start_metrics_server_binds_once() -> None:
    with patch("src.telemetry.server.start_http_server") as mock_start:
        start_metrics_server(9099)

    mock_start.assert_called_once_with(9099)
    assert metrics_server._started is True


def test_start_metrics_server_is_idempotent() -> None:
    with patch("src.telemetry.server.start_http_server") as mock_start:
        start_metrics_server(9099)
        start_metrics_server(9099)

    mock_start.assert_called_once()
