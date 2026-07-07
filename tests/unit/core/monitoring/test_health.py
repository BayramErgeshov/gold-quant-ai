"""Unit tests for health check aggregation."""

from __future__ import annotations

import pytest

from src.core.diagnostics import CheckResult
from src.core.monitoring.health import build_health_report

pytestmark = pytest.mark.unit


def _check(name: str, *, healthy: bool, critical: bool = True) -> CheckResult:
    return CheckResult(name=name, healthy=healthy, detail="ok", duration_ms=1.0, critical=critical)


def test_healthy_when_every_critical_check_passes() -> None:
    report = build_health_report([_check("postgres", healthy=True), _check("redis", healthy=True)])

    assert report.healthy is True


def test_unhealthy_when_a_critical_check_fails() -> None:
    report = build_health_report(
        [_check("postgres", healthy=True), _check("redis", healthy=False)]
    )

    assert report.healthy is False


def test_healthy_despite_non_critical_failure() -> None:
    report = build_health_report(
        [_check("postgres", healthy=True), _check("optional_cache", healthy=False, critical=False)]
    )

    assert report.healthy is True


def test_healthy_for_no_checks() -> None:
    report = build_health_report([])

    assert report.healthy is True
    assert report.checks == []


def test_to_dict_serializes_every_check() -> None:
    report = build_health_report([_check("postgres", healthy=True)])

    serialized = report.to_dict()

    assert serialized["healthy"] is True
    assert serialized["checks"] == [
        {"name": "postgres", "healthy": True, "detail": "ok", "duration_ms": 1.0, "critical": True}
    ]
