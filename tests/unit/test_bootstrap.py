"""Unit tests for `src.bootstrap`."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.bootstrap import bootstrap, main
from src.core.diagnostics import CheckResult

pytestmark = pytest.mark.unit

_HEALTHY_RESULTS = [
    CheckResult(name="postgres", healthy=True, detail="ok", duration_ms=1.0),
    CheckResult(name="redis", healthy=True, detail="ok", duration_ms=1.0),
    CheckResult(name="qdrant", healthy=True, detail="ok", duration_ms=1.0),
]

_DEGRADED_RESULTS = [
    CheckResult(name="postgres", healthy=False, detail="refused", duration_ms=1.0),
    CheckResult(name="redis", healthy=True, detail="ok", duration_ms=1.0),
    CheckResult(name="qdrant", healthy=True, detail="ok", duration_ms=1.0),
]


async def test_bootstrap_returns_true_when_all_checks_healthy() -> None:
    with (
        patch("src.bootstrap.run_startup_diagnostics", AsyncMock(return_value=_HEALTHY_RESULTS)),
        patch("src.bootstrap.start_metrics_server") as mock_start_metrics,
    ):
        healthy = await bootstrap()

    assert healthy is True
    mock_start_metrics.assert_called_once()


async def test_bootstrap_returns_false_when_critical_check_fails() -> None:
    with (
        patch(
            "src.bootstrap.run_startup_diagnostics", AsyncMock(return_value=_DEGRADED_RESULTS)
        ),
        patch("src.bootstrap.start_metrics_server"),
    ):
        healthy = await bootstrap()

    assert healthy is False


def test_main_returns_zero_on_healthy_bootstrap() -> None:
    with patch("src.bootstrap.bootstrap", AsyncMock(return_value=True)):
        assert main() == 0


def test_main_returns_one_on_degraded_bootstrap() -> None:
    with patch("src.bootstrap.bootstrap", AsyncMock(return_value=False)):
        assert main() == 1
