"""Unit tests for system resource metric collection."""

from __future__ import annotations

import pytest

from src.core.monitoring.system_metrics import collect_system_metrics

pytestmark = pytest.mark.unit


def test_collect_system_metrics_returns_plausible_percentages() -> None:
    snapshot = collect_system_metrics()

    assert 0.0 <= snapshot.cpu_percent <= 100.0
    assert 0.0 <= snapshot.memory_percent <= 100.0
    assert 0.0 <= snapshot.disk_percent <= 100.0
