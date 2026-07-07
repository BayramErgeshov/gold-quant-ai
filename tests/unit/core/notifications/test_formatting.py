"""Unit tests for Telegram message formatting."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from src.core.notifications.formatting import (
    DailyReportData,
    ErrorReportData,
    SignalMessageData,
    format_approval_request,
    format_daily_report,
    format_error_report,
    format_news_alert,
    format_signal_message,
    format_trade_closed_message,
)
from src.models.improvement_proposal import ImprovementProposal
from src.models.news_article import NewsArticle
from src.models.trade import Trade

pytestmark = pytest.mark.unit

_SYMBOL_ID = uuid.uuid4()
_TIMESTAMP = datetime(2026, 1, 1, tzinfo=UTC)


def test_format_signal_message_includes_all_key_fields() -> None:
    data = SignalMessageData(
        trade_id="journal-123",
        timestamp=_TIMESTAMP,
        market="XAUUSD",
        direction="BUY",
        entry_price=3362.50,
        stop_loss=3352.80,
        targets=[3375.0, 3388.0, 3405.0],
        confidence_pct=83.0,
        quality_grade="AA",
        reason_summary="Trend, liquidity, macro alignment.",
        alternative_scenario="Reversal below 3352.80.",
        risk_summary="Moderate.",
    )

    text = format_signal_message(data)

    assert "XAUUSD BUY" in text
    assert "3362.50" in text
    assert "3352.80" in text
    assert "3375.00, 3388.00, 3405.00" in text
    assert "83%" in text
    assert "AA" in text
    assert "journal-123" in text


def test_format_signal_message_handles_no_targets() -> None:
    data = SignalMessageData(
        trade_id="journal-123",
        timestamp=_TIMESTAMP,
        market="XAUUSD",
        direction="BUY",
        entry_price=3362.50,
        stop_loss=3352.80,
        targets=[],
        confidence_pct=83.0,
        quality_grade="AA",
        reason_summary="x",
        alternative_scenario="y",
        risk_summary="z",
    )

    text = format_signal_message(data)

    assert "Targets: N/A" in text


def _trade(**overrides: object) -> Trade:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "symbol_id": _SYMBOL_ID,
        "direction": "buy",
        "status": "closed",
        "volume": 1.0,
        "entry_price": 2000.0,
        "stop_loss": 1990.0,
        "exit_price": 2020.0,
        "magic_number": 42,
        "realized_pnl": 20.0,
    }
    defaults.update(overrides)
    return Trade(**defaults)  # type: ignore[arg-type]


def test_format_trade_closed_message_raises_without_prices() -> None:
    with pytest.raises(ValueError, match="entry_price"):
        format_trade_closed_message(_trade(entry_price=None))


def test_format_trade_closed_message_includes_key_fields() -> None:
    trade = _trade(
        opened_at=_TIMESTAMP, closed_at=_TIMESTAMP + timedelta(hours=4)
    )

    text = format_trade_closed_message(trade)

    assert "Entry: 2000.00" in text
    assert "Exit: 2020.00" in text
    assert "4:00:00" in text
    assert "Profit: 20.00" in text
    assert str(trade.id) in text


def test_format_trade_closed_message_labels_loss() -> None:
    trade = _trade(realized_pnl=-15.0)

    text = format_trade_closed_message(trade)

    assert "Loss: -15.00" in text


def test_format_trade_closed_message_includes_prediction_accuracy_when_given() -> None:
    trade = _trade()

    text = format_trade_closed_message(trade, prediction_accuracy="High")

    assert "Prediction accuracy: High" in text


def test_format_daily_report_includes_key_fields() -> None:
    data = DailyReportData(
        report_date="2026-01-01",
        total_signals=10,
        executed_trades=5,
        winning_trades=3,
        losing_trades=2,
        win_rate=0.6,
        profit_factor=1.8,
        net_result_pct=2.5,
    )

    text = format_daily_report(data)

    assert "2026-01-01" in text
    assert "Signals: 10" in text
    assert "win rate 60%" in text
    assert "Profit factor: 1.80" in text
    assert "+2.50%" in text
    assert "OK" in text


def test_format_news_alert_includes_key_fields() -> None:
    article = NewsArticle(
        title="Fed holds rates steady",
        source="reuters.com",
        published_at=_TIMESTAMP,
        content_hash="abc",
        importance_score=0.8,
        expected_volatility="high",
        category="central_bank",
    )

    text = format_news_alert(article)

    assert "Fed holds rates steady" in text
    assert "reuters.com" in text
    assert "0.80" in text
    assert "high" in text
    assert "central_bank" in text


def test_format_news_alert_handles_unclassified_category() -> None:
    article = NewsArticle(
        title="x",
        source="y",
        published_at=_TIMESTAMP,
        content_hash="abc",
        importance_score=0.0,
        expected_volatility="low",
    )

    text = format_news_alert(article)

    assert "unclassified" in text


def test_format_error_report_includes_key_fields() -> None:
    data = ErrorReportData(
        timestamp=_TIMESTAMP,
        module="mt5_client",
        error="Connection timeout",
        severity="high",
        automatic_recovery=True,
        manual_action_required=False,
        status="monitoring",
    )

    text = format_error_report(data)

    assert "[HIGH]" in text
    assert "mt5_client" in text
    assert "Connection timeout" in text
    assert "Auto-recovered: yes" in text
    assert "Manual action required: no" in text
    assert "monitoring" in text


def test_format_approval_request_includes_key_fields() -> None:
    proposal = ImprovementProposal(
        id=uuid.uuid4(),
        title="Widen stops",
        problem="Premature stop-outs.",
        evidence="12 trades.",
        expected_benefit="Fewer stop-outs.",
        potential_risk="Larger losses if wrong.",
        implementation_difficulty="medium",
        recommendation="Backtest wider stops.",
        status="pending",
    )

    text = format_approval_request(proposal)

    assert "Widen stops" in text
    assert "Premature stop-outs." in text
    assert "Approve / Reject / Postpone" in text
    assert str(proposal.id) in text
