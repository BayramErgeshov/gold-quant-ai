"""Unit tests for `src.telemetry.metrics`."""

from __future__ import annotations

import pytest

from src.telemetry.metrics import (
    PLATFORM_UP,
    STARTUP_CHECK_HEALTHY,
    record_platform_health,
    record_startup_check,
)

pytestmark = pytest.mark.unit


def test_record_startup_check_healthy_sets_gauge_to_one() -> None:
    record_startup_check("postgres", healthy=True, duration_ms=12.5)

    assert STARTUP_CHECK_HEALTHY.labels(check="postgres")._value.get() == 1.0


def test_record_startup_check_unhealthy_sets_gauge_to_zero() -> None:
    record_startup_check("redis", healthy=False, duration_ms=5.0)

    assert STARTUP_CHECK_HEALTHY.labels(check="redis")._value.get() == 0.0


def test_record_platform_health_healthy() -> None:
    record_platform_health(True)

    assert PLATFORM_UP._value.get() == 1.0


def test_record_platform_health_unhealthy() -> None:
    record_platform_health(False)

    assert PLATFORM_UP._value.get() == 0.0
