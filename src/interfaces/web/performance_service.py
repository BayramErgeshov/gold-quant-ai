"""Data assembly for the Performance Validation Framework's API endpoint.

Per the "Performance Validation Framework" production requirement:
"Automatically calculate after every closed trade" the full statistics
suite, plus each department's measured contribution/false-positive/
false-negative rates -- "Determine which departments consistently
improve vs reduce decision quality." This module only assembles
already-computed statistics for the web UI; it never recomputes a
department's historical vote (that would require replaying the original
decision), only reads what was actually snapshotted at signal time.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from src.engines.learning_engine.department_performance import (
    DepartmentPerformance,
    compute_department_reliability,
)
from src.engines.statistics_engine.trade_performance_report import (
    PerformanceReport,
    build_performance_report,
)
from src.repositories.trade_repository import TradeRepository

# This research platform is nowhere near this many closed trades; a
# generous cap rather than true unbounded pagination, matching
# `src.interfaces.web.dashboard_service._CLOSED_TRADES_FOR_METRICS`'s own
# "read everything durable, never invent a value" approach.
_MAX_CLOSED_TRADES_FOR_REPORT = 5000


@dataclass(frozen=True, slots=True)
class PerformancePageView:
    """Everything the Performance page/API needs.

    Attributes:
        report: The full trade performance statistics report.
        department_performance: Each department's measured accuracy,
            contribution to wins/losses, and false positive/negative
            rates, keyed by department name.
    """

    report: PerformanceReport = field(default_factory=PerformanceReport)
    department_performance: dict[str, DepartmentPerformance] = field(default_factory=dict)


async def get_performance_page(session: AsyncSession) -> PerformancePageView:
    """Assemble the current Performance Validation Framework view.

    Args:
        session: The active database session.

    Returns:
        A `PerformancePageView` computed entirely from persisted, closed
        `Trade` rows -- never a simulated or fabricated statistic.
    """
    closed_trades = await TradeRepository(session).list_by_status(
        "closed", limit=_MAX_CLOSED_TRADES_FOR_REPORT
    )
    return PerformancePageView(
        report=build_performance_report(closed_trades),
        department_performance=compute_department_reliability(closed_trades),
    )
