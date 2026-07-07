"""Unit tests for per-agent health tracking."""

from __future__ import annotations

import pytest

from src.core.monitoring.agent_health import AgentHealthRegistry

pytestmark = pytest.mark.unit


def test_get_returns_none_for_untracked_agent() -> None:
    registry = AgentHealthRegistry()

    assert registry.get("trend_agent") is None


def test_track_records_successful_run() -> None:
    registry = AgentHealthRegistry()

    result = registry.track("trend_agent", lambda: "report")

    assert result == "report"
    health = registry.get("trend_agent")
    assert health is not None
    assert health.last_run_healthy is True
    assert health.total_runs == 1
    assert health.total_failures == 0
    assert health.last_latency_ms >= 0.0


def test_track_records_failed_run_and_reraises() -> None:
    registry = AgentHealthRegistry()

    def _failing() -> None:
        raise RuntimeError("agent exploded")

    with pytest.raises(RuntimeError, match="agent exploded"):
        registry.track("trend_agent", _failing)

    health = registry.get("trend_agent")
    assert health is not None
    assert health.last_run_healthy is False
    assert health.total_runs == 1
    assert health.total_failures == 1


def test_track_accumulates_across_multiple_runs() -> None:
    registry = AgentHealthRegistry()

    registry.track("trend_agent", lambda: "ok")
    with pytest.raises(RuntimeError):
        registry.track("trend_agent", lambda: (_ for _ in ()).throw(RuntimeError("x")))
    registry.track("trend_agent", lambda: "ok again")

    health = registry.get("trend_agent")
    assert health is not None
    assert health.total_runs == 3
    assert health.total_failures == 1
    assert health.last_run_healthy is True


def test_all_statuses_lists_every_tracked_agent() -> None:
    registry = AgentHealthRegistry()
    registry.track("trend_agent", lambda: "ok")
    registry.track("liquidity_agent", lambda: "ok")

    names = {status.name for status in registry.all_statuses()}

    assert names == {"trend_agent", "liquidity_agent"}
