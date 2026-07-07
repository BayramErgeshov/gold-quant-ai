"""Per-agent health tracking for the Observability API.

Per OBSERVABILITY_AND_MONITORING.md "AI Agent Metrics": "Every Agent...
Status, Runtime, Latency... Failures." Agents in this platform are
stateless, synchronously-invoked analysis calls rather than long-running
processes, so tracking happens per-call: each call's latency and outcome
update that agent's rolling status.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TypeVar

from src.telemetry.metrics import (
    AGENT_LAST_RUN_HEALTHY,
    AGENT_RUN_DURATION_SECONDS,
    AGENT_RUN_FAILURES_TOTAL,
)

_ResultT = TypeVar("_ResultT")


@dataclass(slots=True)
class AgentHealth:
    """One agent's rolling health status.

    Attributes:
        name: Agent name.
        last_run_healthy: Whether the most recent run succeeded.
        last_latency_ms: The most recent run's duration, in milliseconds.
        total_runs: Total number of tracked runs.
        total_failures: Total number of failed runs.
    """

    name: str
    last_run_healthy: bool = True
    last_latency_ms: float = 0.0
    total_runs: int = 0
    total_failures: int = 0


@dataclass(slots=True)
class AgentHealthRegistry:
    """In-memory registry of every tracked agent's rolling health status."""

    _agents: dict[str, AgentHealth] = field(default_factory=dict)

    def track(self, agent_name: str, fn: Callable[[], _ResultT]) -> _ResultT:
        """Run `fn`, recording its latency and success/failure for `agent_name`.

        Args:
            agent_name: The agent's name (AGENT_SYSTEM.md: every agent has a name).
            fn: The zero-argument call to run, e.g. `lambda: agent.analyze(candles)`.

        Returns:
            `fn`'s return value, unmodified.

        Raises:
            Exception: Whatever `fn` raises, after recording the failure —
                never swallowed (AGENT_SYSTEM.md: "Agents never hide uncertainty").
        """
        health = self._agents.setdefault(agent_name, AgentHealth(name=agent_name))
        started_at = time.perf_counter()
        try:
            result = fn()
        except Exception:
            health.last_latency_ms = (time.perf_counter() - started_at) * 1000
            health.total_runs += 1
            health.total_failures += 1
            health.last_run_healthy = False
            AGENT_LAST_RUN_HEALTHY.labels(agent=agent_name).set(0.0)
            AGENT_RUN_FAILURES_TOTAL.labels(agent=agent_name).inc()
            AGENT_RUN_DURATION_SECONDS.labels(agent=agent_name).observe(
                health.last_latency_ms / 1000
            )
            raise

        health.last_latency_ms = (time.perf_counter() - started_at) * 1000
        health.total_runs += 1
        health.last_run_healthy = True
        AGENT_LAST_RUN_HEALTHY.labels(agent=agent_name).set(1.0)
        AGENT_RUN_DURATION_SECONDS.labels(agent=agent_name).observe(health.last_latency_ms / 1000)
        return result

    def get(self, agent_name: str) -> AgentHealth | None:
        """Fetch an agent's current health status, if tracked.

        Args:
            agent_name: The agent's name.

        Returns:
            The `AgentHealth`, or None if `agent_name` has never been tracked.
        """
        return self._agents.get(agent_name)

    def all_statuses(self) -> list[AgentHealth]:
        """List every tracked agent's health status."""
        return list(self._agents.values())
