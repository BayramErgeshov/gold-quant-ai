"""Prometheus metrics for GOLD QUANT AI.

Exposes process-level and startup-diagnostic metrics per
OBSERVABILITY_AND_MONITORING.md ("Everything must be measurable. Every
module exposes Health Status, Latency, Error Count..."). Engine-specific
metrics (agent latency, trade counters, decision confidence, ...) are added
alongside the engines that produce them in later roadmap phases.

Process-level CPU/memory/GC metrics are provided automatically by
`prometheus_client`'s default collectors, registered on import.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram, Info

PLATFORM_INFO = Info(
    "gold_quant_ai", "Static platform build information (environment, version)."
)

PLATFORM_UP = Gauge(
    "gold_quant_ai_up",
    "Whether the platform completed startup diagnostics successfully (1) or not (0).",
)

STARTUP_CHECK_HEALTHY = Gauge(
    "gold_quant_ai_startup_check_healthy",
    "Whether a given startup dependency check passed (1) or failed (0).",
    labelnames=("check",),
)

STARTUP_CHECK_DURATION_SECONDS = Histogram(
    "gold_quant_ai_startup_check_duration_seconds",
    "Duration of each startup dependency check, in seconds.",
    labelnames=("check",),
)


def record_startup_check(name: str, healthy: bool, duration_ms: float) -> None:
    """Record the outcome of a single startup diagnostic check.

    Args:
        name: Check name, e.g. "postgres".
        healthy: Whether the check succeeded.
        duration_ms: Check duration in milliseconds.
    """
    STARTUP_CHECK_HEALTHY.labels(check=name).set(1.0 if healthy else 0.0)
    STARTUP_CHECK_DURATION_SECONDS.labels(check=name).observe(duration_ms / 1000)


def record_platform_health(healthy: bool) -> None:
    """Record overall platform health after startup diagnostics.

    Args:
        healthy: True if every critical dependency is healthy.
    """
    PLATFORM_UP.set(1.0 if healthy else 0.0)


# Phase 17 (Monitoring): AI Agent Metrics (OBSERVABILITY_AND_MONITORING.md
# "AI Agent Metrics": "Every Agent... Status, Runtime, Latency... Failures").
AGENT_LAST_RUN_HEALTHY = Gauge(
    "gold_quant_ai_agent_last_run_healthy",
    "Whether an agent's most recent run succeeded (1) or failed (0).",
    labelnames=("agent",),
)

AGENT_RUN_DURATION_SECONDS = Histogram(
    "gold_quant_ai_agent_run_duration_seconds",
    "Duration of each agent run, in seconds.",
    labelnames=("agent",),
)

AGENT_RUN_FAILURES_TOTAL = Counter(
    "gold_quant_ai_agent_run_failures_total",
    "Total number of failed agent runs.",
    labelnames=("agent",),
)

# Phase 17 (Monitoring): Infrastructure Metrics
# (OBSERVABILITY_AND_MONITORING.md "Infrastructure Metrics": "Monitor CPU, RAM, Disk...").
CPU_USAGE_PERCENT = Gauge(
    "gold_quant_ai_cpu_usage_percent", "Host CPU utilization, in percent."
)

MEMORY_USAGE_PERCENT = Gauge(
    "gold_quant_ai_memory_usage_percent", "Host memory utilization, in percent."
)

DISK_USAGE_PERCENT = Gauge(
    "gold_quant_ai_disk_usage_percent", "Filesystem utilization, in percent.", labelnames=("path",)
)
