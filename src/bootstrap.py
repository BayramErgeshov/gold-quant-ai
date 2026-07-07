"""Startup entrypoint for GOLD QUANT AI.

Implements the "Startup Workflow" from WORKFLOW_ENGINE.md for the
capabilities that exist at this stage of IMPLEMENTATION_ROADMAP.md: load
configuration, configure logging, and verify that every critical piece of
infrastructure (PostgreSQL, Redis, Qdrant) is reachable.

Per FAILSAFE_PROTOCOL.md, a failed critical dependency must never crash the
process outright — it is reported clearly and the platform does not proceed
to trading. The persistent supervisory loop (scheduler, market monitoring,
Chief AI) is introduced once the Workflow Engine and research departments
exist (later roadmap phases); today, this entrypoint performs one diagnostic
pass and exits with a status code reflecting platform health, so it can be
used directly as a container healthcheck / CI smoke test.
"""

from __future__ import annotations

import asyncio
import sys

from src.common.logging import configure_logging, get_logger
from src.core.diagnostics import CheckResult, run_startup_diagnostics
from src.settings import Settings, get_settings
from src.telemetry.metrics import (
    PLATFORM_INFO,
    record_platform_health,
    record_startup_check,
)
from src.telemetry.server import start_metrics_server

_EXIT_HEALTHY = 0
_EXIT_CRITICAL_FAILURE = 1


def _log_diagnostic_results(results: list[CheckResult]) -> bool:
    """Log every diagnostic result and report overall critical health.

    Args:
        results: Output of `run_startup_diagnostics`.

    Returns:
        True if every critical check passed, False otherwise.
    """
    logger = get_logger(__name__)
    all_critical_healthy = True

    for result in results:
        log_method = logger.info if result.healthy else logger.error
        log_method(
            "startup_check",
            check=result.name,
            healthy=result.healthy,
            critical=result.critical,
            detail=result.detail,
            duration_ms=round(result.duration_ms, 2),
        )
        record_startup_check(result.name, result.healthy, result.duration_ms)
        if result.critical and not result.healthy:
            all_critical_healthy = False

    return all_critical_healthy


async def bootstrap() -> bool:
    """Load settings, configure logging and run startup diagnostics.

    Returns:
        True if the platform is healthy enough to proceed, False otherwise.
    """
    settings: Settings = get_settings()
    configure_logging(settings)
    logger = get_logger(__name__)

    logger.info(
        "gold_quant_ai_starting",
        environment=settings.environment,
        primary_symbol=settings.platform.symbols.primary,
        live_trading_enabled=settings.platform.execution.live_enabled,
    )

    PLATFORM_INFO.info({"environment": settings.environment, "version": "1.0.0"})
    if settings.platform.monitoring.prometheus.get("enabled", False):
        start_metrics_server(settings.monitoring_env.prometheus_port)

    results = await run_startup_diagnostics(settings)
    healthy = _log_diagnostic_results(results)
    record_platform_health(healthy)

    if healthy:
        logger.info("gold_quant_ai_startup_complete", status="healthy")
    else:
        logger.critical(
            "gold_quant_ai_startup_degraded",
            status="critical_dependency_unavailable",
            action="trading_disabled_diagnostics_only",
        )

    return healthy


def main() -> int:
    """Synchronous process entrypoint.

    Returns:
        Process exit code: 0 if healthy, 1 if a critical dependency failed.
    """
    healthy = asyncio.run(bootstrap())
    return _EXIT_HEALTHY if healthy else _EXIT_CRITICAL_FAILURE


if __name__ == "__main__":  # pragma: no cover - exercised via container entrypoint, not tests
    sys.exit(main())
