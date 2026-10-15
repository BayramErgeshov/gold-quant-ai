"""Unit tests for the Performance Validation Framework's trade report."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from src.engines.statistics_engine.trade_performance_report import (
    PerformanceReport,
    build_performance_report,
    classify_confidence_range,
    classify_strategy,
    classify_trading_session,
)
from src.models.trade import Trade

pytestmark = pytest.mark.unit

_SYMBOL_ID = uuid.uuid4()
_BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


def _closed_trade(**overrides: object) -> Trade:
    defaults: dict[str, object] = {
        "symbol_id": _SYMBOL_ID,
        "direction": "buy",
        "status": "closed",
        "volume": 1.0,
        "entry_price": 2000.0,
        "stop_loss": 1990.0,
        "exit_price": 2010.0,
        "realized_pnl": 10.0,
        "magic_number": 1,
        "opened_at": _BASE_TIME,
        "closed_at": _BASE_TIME + timedelta(hours=2),
    }
    defaults.update(overrides)
    return Trade(**defaults)


def test_classify_strategy_reads_department_votes() -> None:
    assert classify_strategy({"scalping_engine": {"bias": "bullish"}}) == "Scalping"
    assert classify_strategy({"swing_engine": {"bias": "bullish"}}) == "Swing"
    assert classify_strategy({"shakky_engine": {"bias": "bullish"}}) == "Shakky"
    assert classify_strategy({"micro_scalping_engine": {"bias": "bullish"}}) == "MicroScalping"
    assert classify_strategy({"technical": {"bias": "bullish"}}) == "Intraday"
    assert classify_strategy(None) == "unknown"
    assert classify_strategy({}) == "unknown"


def test_classify_trading_session_buckets_utc_hours() -> None:
    assert classify_trading_session(datetime(2026, 1, 1, 3, tzinfo=UTC)) == "asian"
    assert classify_trading_session(datetime(2026, 1, 1, 9, tzinfo=UTC)) == "london"
    assert classify_trading_session(datetime(2026, 1, 1, 14, tzinfo=UTC)) == "london_ny_overlap"
    assert classify_trading_session(datetime(2026, 1, 1, 19, tzinfo=UTC)) == "new_york"
    assert classify_trading_session(datetime(2026, 1, 1, 23, tzinfo=UTC)) == "off_hours"


def test_classify_trading_session_treats_naive_timestamps_as_utc() -> None:
    assert classify_trading_session(datetime(2026, 1, 1, 3)) == "asian"  # noqa: DTZ001


def test_classify_confidence_range_buckets_correctly() -> None:
    assert classify_confidence_range(None) == "unknown"
    assert classify_confidence_range(55.0) == "50-60%"
    assert classify_confidence_range(95.0) == "90-100%"
    assert classify_confidence_range(10.0) == "unknown"


def test_build_performance_report_returns_defaults_for_no_trades() -> None:
    report = build_performance_report([])

    assert report == PerformanceReport()


def test_build_performance_report_ignores_trades_missing_entry_or_exit_price() -> None:
    trade = _closed_trade(exit_price=None)

    report = build_performance_report([trade])

    assert report.trade_count == 0


def test_build_performance_report_computes_core_metrics() -> None:
    winner = _closed_trade(realized_pnl=100.0, exit_price=2010.0)
    # A sell trade loses when price rises against the short.
    loser = _closed_trade(realized_pnl=-50.0, exit_price=2010.0, direction="sell")

    report = build_performance_report([winner, loser])

    assert report.trade_count == 2
    assert report.win_rate == pytest.approx(0.5)
    assert report.max_consecutive_wins == 1
    assert report.max_consecutive_losses == 1
    assert report.average_holding_time == timedelta(hours=2)


def test_build_performance_report_segments_by_strategy() -> None:
    intraday = _closed_trade(department_votes={"technical": {"bias": "bullish"}})
    scalp = _closed_trade(department_votes={"scalping_engine": {"bias": "bullish"}})

    report = build_performance_report([intraday, scalp])

    segments = {s.segment: s for s in report.profit_by_strategy}
    assert "Intraday" in segments
    assert "Scalping" in segments
    assert segments["Intraday"].trade_count == 1
    assert segments["Scalping"].trade_count == 1


def test_build_performance_report_segments_by_market_regime_and_confidence() -> None:
    trade = _closed_trade(market_regime="bull_trend", confidence_pct=82.0)
    unlabeled = _closed_trade(market_regime=None, confidence_pct=None)

    report = build_performance_report([trade, unlabeled])

    regimes = {s.segment for s in report.profit_by_market_regime}
    confidences = {s.segment for s in report.profit_by_confidence_range}
    assert "bull_trend" in regimes
    assert "unknown" in regimes
    assert "80-90%" in confidences
    assert "unknown" in confidences


def test_build_performance_report_recovery_and_calmar_are_zero_for_a_single_trade() -> None:
    report = build_performance_report([_closed_trade()])

    # A single trade has no drawdown to recover from and no multi-day
    # period to annualize over -- both must honestly read 0.0.
    assert report.recovery_factor == 0.0
    assert report.calmar_ratio == 0.0
