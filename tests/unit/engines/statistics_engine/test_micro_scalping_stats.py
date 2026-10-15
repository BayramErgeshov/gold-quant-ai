"""Unit tests for Micro Scalping's own daily/hourly statistics."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from src.engines.statistics_engine.micro_scalping_stats import compute_micro_scalping_daily_stats
from src.models.trade import Trade

pytestmark = pytest.mark.unit

_SYMBOL_ID = uuid.uuid4()


def _trade(*, opened_at: datetime, closed_at: datetime, realized_pnl: float) -> Trade:
    return Trade(
        symbol_id=_SYMBOL_ID,
        direction="buy",
        status="closed",
        volume=0.05,
        stop_loss=1998.0,
        magic_number=99,
        opened_at=opened_at,
        closed_at=closed_at,
        realized_pnl=realized_pnl,
    )


def test_returns_honest_defaults_for_no_trades() -> None:
    stats = compute_micro_scalping_daily_stats([])

    assert stats.trades_per_day == 0.0
    assert stats.today_total_profit_usd == 0.0
    assert stats.best_trading_hour_utc is None
    assert stats.worst_trading_hour_utc is None


def test_ignores_trades_without_opened_at() -> None:
    trade = _trade(
        opened_at=datetime(2026, 1, 5, 10, tzinfo=UTC),
        closed_at=datetime(2026, 1, 5, 10, 2, tzinfo=UTC),
        realized_pnl=1.0,
    )
    trade.opened_at = None

    stats = compute_micro_scalping_daily_stats([trade])

    assert stats.trades_per_day == 0.0


def test_computes_trades_per_day_across_distinct_calendar_days() -> None:
    trades = [
        _trade(
            opened_at=datetime(2026, 1, 5, 10, tzinfo=UTC),
            closed_at=datetime(2026, 1, 5, 10, 2, tzinfo=UTC),
            realized_pnl=1.0,
        ),
        _trade(
            opened_at=datetime(2026, 1, 5, 11, tzinfo=UTC),
            closed_at=datetime(2026, 1, 5, 11, 2, tzinfo=UTC),
            realized_pnl=1.0,
        ),
        _trade(
            opened_at=datetime(2026, 1, 6, 9, tzinfo=UTC),
            closed_at=datetime(2026, 1, 6, 9, 2, tzinfo=UTC),
            realized_pnl=1.0,
        ),
    ]

    stats = compute_micro_scalping_daily_stats(trades)

    assert stats.trades_per_day == pytest.approx(1.5)


def test_today_total_profit_only_sums_trades_closed_today() -> None:
    now = datetime(2026, 1, 6, 15, tzinfo=UTC)
    trades = [
        _trade(
            opened_at=now - timedelta(days=1),
            closed_at=now - timedelta(days=1),
            realized_pnl=5.0,
        ),
        _trade(opened_at=now, closed_at=now, realized_pnl=1.5),
        _trade(opened_at=now, closed_at=now, realized_pnl=-0.5),
    ]

    stats = compute_micro_scalping_daily_stats(trades, now=now)

    assert stats.today_total_profit_usd == pytest.approx(1.0)


def test_best_and_worst_trading_hour_reflect_total_profit_per_hour() -> None:
    trades = [
        _trade(
            opened_at=datetime(2026, 1, 5, 9, tzinfo=UTC),
            closed_at=datetime(2026, 1, 5, 9, 2, tzinfo=UTC),
            realized_pnl=5.0,
        ),
        _trade(
            opened_at=datetime(2026, 1, 6, 9, tzinfo=UTC),
            closed_at=datetime(2026, 1, 6, 9, 2, tzinfo=UTC),
            realized_pnl=3.0,
        ),
        _trade(
            opened_at=datetime(2026, 1, 5, 14, tzinfo=UTC),
            closed_at=datetime(2026, 1, 5, 14, 2, tzinfo=UTC),
            realized_pnl=-4.0,
        ),
    ]

    stats = compute_micro_scalping_daily_stats(trades)

    assert stats.best_trading_hour_utc == 9
    assert stats.worst_trading_hour_utc == 14
