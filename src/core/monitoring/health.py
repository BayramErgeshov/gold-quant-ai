"""Health check aggregation for the Observability API.

Per OBSERVABILITY_AND_MONITORING.md "Observability API": "Expose Health,
Metrics, Status, Version..." Aggregates every infrastructure check
(`src.core.diagnostics`) into one JSON-serializable report.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.core.diagnostics import CheckResult


@dataclass(frozen=True, slots=True)
class HealthReport:
    """Aggregate platform health across every checked dependency.

    Attributes:
        healthy: True only if every *critical* check passed.
        checks: Every individual `CheckResult`.
    """

    healthy: bool
    checks: list[CheckResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        """Serialize to a JSON-friendly dict for the `/health` endpoint."""
        return {
            "healthy": self.healthy,
            "checks": [
                {
                    "name": check.name,
                    "healthy": check.healthy,
                    "detail": check.detail,
                    "duration_ms": check.duration_ms,
                    "critical": check.critical,
                }
                for check in self.checks
            ],
        }


def build_health_report(checks: list[CheckResult]) -> HealthReport:
    """Aggregate individual checks into one platform-wide health report.

    Args:
        checks: Every `CheckResult`, e.g. from
            `src.core.diagnostics.run_startup_diagnostics`.

    Returns:
        A `HealthReport`. `healthy` is False if any *critical* check
        failed; a failing non-critical check does not mark the platform
        unhealthy overall (FAILSAFE_PROTOCOL.md: degraded-but-observable
        operation rather than an all-or-nothing outage).
    """
    healthy = all(check.healthy for check in checks if check.critical)
    return HealthReport(healthy=healthy, checks=checks)
