"""Unit tests for backtest report generation."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.engines.backtesting_engine.report import build_report
from src.engines.backtesting_engine.simulator import BacktestRun, SimulatedTrade

pytestmark = pytest.mark.unit

_TIMESTAMP = datetime(2026, 1, 1, tzinfo=UTC)


def _trade(return_pct: float) -> SimulatedTrade:
    return SimulatedTrade(
        direction="buy",
        entry_timestamp=_TIMESTAMP,
        entry_price=100.0,
        exit_timestamp=_TIMESTAMP,
        exit_price=100.0 * (1 + return_pct / 100),
        exit_reason="take_profit",
        return_pct=return_pct,
    )


def test_build_report_computes_quantitative_fields() -> None:
    run = BacktestRun(
        trades=[_trade(5.0), _trade(-2.0), _trade(3.0)],
        equity_curve=[10_000.0, 10_500.0, 10_290.0, 10_598.7],
    )

    report = build_report(run, strategy_name="xauusd_h1_trend", strategy_version="1.0.0")

    assert report.strategy_name == "xauusd_h1_trend"
    assert report.trade_count == 3
    assert report.win_rate == pytest.approx(2 / 3)
    assert report.final_equity == pytest.approx(10_598.7)
    assert report.strengths == []
    assert report.weaknesses == []


def test_build_report_accepts_qualitative_fields() -> None:
    run = BacktestRun(trades=[_trade(1.0)], equity_curve=[10_000.0, 10_100.0])

    report = build_report(
        run,
        strategy_name="xauusd_h1_trend",
        strategy_version="1.0.0",
        strengths=["Consistent in trending regimes"],
        weaknesses=["Underperforms in ranges"],
    )

    assert report.strengths == ["Consistent in trending regimes"]
    assert report.weaknesses == ["Underperforms in ranges"]


def test_build_report_handles_empty_run() -> None:
    run = BacktestRun(trades=[], equity_curve=[])

    report = build_report(run, strategy_name="empty", strategy_version="1.0.0")

    assert report.trade_count == 0
    assert report.final_equity == 0.0
