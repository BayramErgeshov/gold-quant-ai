"""Micro Scalping's own daily/hourly statistics.

Per the engine's own spec ("Win Rate, Profit Factor, Average Profit/Loss,
Average Holding Time, Trades per Day, Total Daily Profit, Best/Worst
Trading Hours"): the first four are already generic
(`src.engines.statistics_engine.trade_performance_report
.build_performance_report`, grouped by `classify_strategy` -- Micro
Scalping is now one of its recognized strategies, same as Scalping/Swing/
Shakky). This module adds only the metrics specific to a high-frequency
engine that no other, slower strategy's own stats card needs: how many
trades it fires per day, today's running total, and which UTC hour has
historically been most/least profitable for it.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime

from src.models.trade import Trade


@dataclass(frozen=True, slots=True)
class MicroScalpingDailyStats:
    """Micro Scalping's own daily/hourly statistics, computed only from closed trades.

    Attributes:
        trades_per_day: Average number of closed trades per distinct
            calendar day (UTC) this engine has traded on. 0.0 if no
            trade has `opened_at` recorded.
        today_total_profit_usd: Sum of `realized_pnl` for trades closed
            today (UTC calendar day) -- the live "Total Daily Profit"
            figure, not a historical average.
        best_trading_hour_utc: The UTC hour (0-23) with the highest total
            realized profit across every closed trade, if any trade has
            a recorded `opened_at`. None if there is no reviewable data.
        worst_trading_hour_utc: Same, for the lowest total realized profit.
    """

    trades_per_day: float = 0.0
    today_total_profit_usd: float = 0.0
    best_trading_hour_utc: int | None = None
    worst_trading_hour_utc: int | None = None


def compute_micro_scalping_daily_stats(
    closed_trades: list[Trade], *, now: datetime | None = None
) -> MicroScalpingDailyStats:
    """Build Micro Scalping's own daily/hourly statistics.

    Args:
        closed_trades: Every closed Micro Scalping trade (magic-number-
            filtered by the caller, mirrors `build_performance_report`'s
            own "caller filters, function only aggregates" convention).
        now: The current time, for "today." Defaults to `datetime.now(UTC)`.

    Returns:
        A `MicroScalpingDailyStats`. All fields default to 0/None if no
        trade has `opened_at` recorded -- never a fabricated statistic.
    """
    reviewable = [trade for trade in closed_trades if trade.opened_at is not None]
    if not reviewable:
        return MicroScalpingDailyStats()

    current_time = now if now is not None else datetime.now(UTC)
    today = current_time.astimezone(UTC).date()

    opened_dates = {trade.opened_at.astimezone(UTC).date() for trade in reviewable}  # type: ignore[union-attr]
    trades_per_day = len(reviewable) / len(opened_dates)

    today_total_profit_usd = sum(
        trade.realized_pnl or 0.0
        for trade in reviewable
        if trade.closed_at is not None and trade.closed_at.astimezone(UTC).date() == today
    )

    profit_by_hour: dict[int, float] = defaultdict(float)
    for trade in reviewable:
        assert trade.opened_at is not None
        profit_by_hour[trade.opened_at.astimezone(UTC).hour] += trade.realized_pnl or 0.0

    best_trading_hour_utc = max(profit_by_hour, key=lambda hour: profit_by_hour[hour])
    worst_trading_hour_utc = min(profit_by_hour, key=lambda hour: profit_by_hour[hour])

    return MicroScalpingDailyStats(
        trades_per_day=trades_per_day,
        today_total_profit_usd=today_total_profit_usd,
        best_trading_hour_utc=best_trading_hour_utc,
        worst_trading_hour_utc=worst_trading_hour_utc,
    )


__all__ = ["MicroScalpingDailyStats", "compute_micro_scalping_daily_stats"]
