"""System resource metrics for the Observability API.

Per OBSERVABILITY_AND_MONITORING.md "Infrastructure Metrics": "Monitor
CPU, RAM, Disk..." Snapshots current host resource usage into Prometheus
gauges. GPU/Temperature/Network/Swap are not collected here — this
platform has no GPU workload yet, and container-level network/swap
metrics are better sourced from Node Exporter/cAdvisor (already part of
the Phase 1 Docker Compose stack, per OBSERVABILITY_AND_MONITORING.md
"Prometheus Exporters") than duplicated in application code.
"""

from __future__ import annotations

from dataclasses import dataclass

import psutil

from src.telemetry.metrics import CPU_USAGE_PERCENT, DISK_USAGE_PERCENT, MEMORY_USAGE_PERCENT

_DEFAULT_DISK_PATH = "/"


@dataclass(frozen=True, slots=True)
class SystemMetricsSnapshot:
    """A single point-in-time system resource reading."""

    cpu_percent: float
    memory_percent: float
    disk_percent: float


def collect_system_metrics(*, disk_path: str = _DEFAULT_DISK_PATH) -> SystemMetricsSnapshot:
    """Snapshot current CPU/memory/disk usage and record it into Prometheus gauges.

    Args:
        disk_path: Filesystem path to measure disk usage for.

    Returns:
        The collected `SystemMetricsSnapshot`.
    """
    cpu_percent = psutil.cpu_percent(interval=None)
    memory_percent = psutil.virtual_memory().percent
    disk_percent = psutil.disk_usage(disk_path).percent

    CPU_USAGE_PERCENT.set(cpu_percent)
    MEMORY_USAGE_PERCENT.set(memory_percent)
    DISK_USAGE_PERCENT.labels(path=disk_path).set(disk_percent)

    return SystemMetricsSnapshot(
        cpu_percent=cpu_percent, memory_percent=memory_percent, disk_percent=disk_percent
    )
