"""Unit tests for Telegram message formatting."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from src.core.notifications.formatting import (
    DailyReportData,
    ErrorReportData,
    NoTradeMessageData,
    PositionEventData,
    SignalMessageData,
    build_no_trade_reasons_ru,
    build_reason_tags_ru,
    build_reason_tags_ru_for_direction,
    format_approval_request,
    format_daily_report,
    format_error_report,
    format_news_alert,
    format_no_trade_message,
    format_position_event_message,
    format_post_mortem_message,
    format_pre_close_report_message,
    format_signal_message,
    format_trade_closed_message,
)
from src.engines.chief_ai.decision import ChiefAIDecision
from src.engines.chief_ai.trade_quality import TradeQualityResult
from src.engines.historical_engine.similarity import SimilarityDisplayStats
from src.engines.learning_engine.post_mortem import PostMortemReport
from src.engines.learning_engine.trade_review import TradeReview
from src.engines.statistics_engine.probability import ProbabilityEstimate
from src.models.improvement_proposal import ImprovementProposal
from src.models.news_article import NewsArticle
from src.models.trade import Trade
from src.workflows.reporting.pre_close_report import PositionPreCloseAssessment

pytestmark = pytest.mark.unit

_SYMBOL_ID = uuid.uuid4()
_TIMESTAMP = datetime(2026, 1, 1, tzinfo=UTC)


def test_build_reason_tags_ru_maps_bias_to_arrows() -> None:
    votes: dict[str, dict[str, float | str]] = {
        "technical": {"bias": "bullish", "confidence": 0.8},
        "correlation": {"bias": "bearish", "confidence": 0.6},
        "ml": {"bias": "neutral", "confidence": 0.1},
    }

    tags = build_reason_tags_ru(votes)

    assert "Технический анализ ↑" in tags
    assert "Корреляция ↓" in tags
    assert not any("ML-модель" in tag for tag in tags)


def test_build_reason_tags_ru_falls_back_to_the_raw_key_for_unknown_departments() -> None:
    tags = build_reason_tags_ru({"some_new_department": {"bias": "bullish", "confidence": 0.5}})

    assert tags == ["some_new_department ↑"]


def test_build_reason_tags_ru_for_direction_marks_agreement_and_disagreement() -> None:
    votes: dict[str, dict[str, float | str]] = {
        "technical": {"bias": "bullish", "confidence": 0.8},
        "correlation": {"bias": "bearish", "confidence": 0.6},
        "ml": {"bias": "neutral", "confidence": 0.1},
    }

    buy_tags = build_reason_tags_ru_for_direction(votes, "BUY")
    sell_tags = build_reason_tags_ru_for_direction(votes, "SELL")

    assert "✅ Технический анализ" in buy_tags
    assert "❌ Корреляция" in buy_tags
    assert not any("ML-модель" in tag for tag in buy_tags)
    # Same votes, opposite executed direction -- agreement/disagreement flips.
    assert "❌ Технический анализ" in sell_tags
    assert "✅ Корреляция" in sell_tags


def test_format_signal_message_buy_includes_all_key_fields() -> None:
    data = SignalMessageData(
        trade_id="journal-123",
        market="XAUUSD",
        direction="BUY",
        strategy_name="xauusd_m15_live_swing",
        entry_price=4075.20,
        stop_loss=4069.50,
        take_profit=4086.30,
        confidence_pct=82.0,
        quality_score=92.0,
        reason_tags=["✅ Тренд", "❌ Корреляция"],
    )

    text = format_signal_message(data)

    assert "🟢 BUY XAUUSD" in text
    assert "📈 Стратегия:\nСвинг" in text
    assert "💰 Вход:\n4075.20" in text
    assert "🛑 SL:\n4069.50" in text
    assert "🎯 TP:\n4086.30" in text
    assert "📊 Уверенность:\n82%" in text
    assert "⭐ Качество:\n92/100" in text
    assert "📌 Причины:" in text
    assert "✅ Тренд" in text
    assert "❌ Корреляция" in text
    assert "🧠 Chief AI:\nПокупка подтверждена." in text
    assert "Журнал: journal-123" in text
    # Per the exact example format: quality/confidence come right after
    # the strategy, before entry/SL/TP.
    assert text.index("Качество") < text.index("Вход")


def test_format_signal_message_sell_uses_the_red_emoji() -> None:
    data = SignalMessageData(
        trade_id="journal-123",
        market="XAUUSD",
        direction="SELL",
        strategy_name="xauusd_m15_live",
        entry_price=4075.20,
        stop_loss=4080.50,
        take_profit=None,
        confidence_pct=70.0,
        quality_score=65.0,
    )

    text = format_signal_message(data)

    assert "🔴 SELL XAUUSD" in text
    assert "📈 Стратегия:\nIntraday" in text
    assert "🧠 Chief AI:\nПродажа подтверждена." in text


def test_format_signal_message_omits_target_and_reason_block_when_absent() -> None:
    data = SignalMessageData(
        trade_id="journal-123",
        market="XAUUSD",
        direction="BUY",
        strategy_name="xauusd_m15_live_scalp",
        entry_price=4075.20,
        stop_loss=4069.50,
        take_profit=None,
        confidence_pct=82.0,
        quality_score=60.0,
    )

    text = format_signal_message(data)

    assert "🎯" not in text
    assert "📌 Причины:" not in text
    assert "📈 Стратегия:\nСкальпинг" in text


def test_format_signal_message_includes_the_similarity_block_when_present() -> None:
    data = SignalMessageData(
        trade_id="journal-123",
        market="XAUUSD",
        direction="BUY",
        strategy_name="xauusd_m15_live_swing",
        entry_price=4075.20,
        stop_loss=4069.50,
        take_profit=4086.30,
        confidence_pct=82.0,
        quality_score=92.0,
        similarity_summary=SimilarityDisplayStats(
            found_count=42,
            profitable_count=28,
            failed_count=14,
            win_rate_pct=66.7,
            average_rr=2.1,
            average_holding_time_minutes=150.0,
            average_drawdown_pct=0.8,
        ),
    )

    text = format_signal_message(data)

    assert "🔍 Похожие ситуации: 42" in text
    assert "Прибыльных: 28" in text
    assert "Провал: 14" in text
    assert "Средний RR: 2.1" in text


def test_format_signal_message_omits_the_similarity_block_when_nothing_was_found() -> None:
    data = SignalMessageData(
        trade_id="journal-123",
        market="XAUUSD",
        direction="BUY",
        strategy_name="xauusd_m15_live",
        entry_price=4075.20,
        stop_loss=4069.50,
        take_profit=None,
        confidence_pct=82.0,
        quality_score=60.0,
        similarity_summary=SimilarityDisplayStats(
            found_count=0,
            profitable_count=0,
            failed_count=0,
            win_rate_pct=None,
            average_rr=None,
            average_holding_time_minutes=150.0,
            average_drawdown_pct=None,
        ),
    )

    text = format_signal_message(data)

    assert "🔍 Похожие ситуации" not in text


def test_format_position_event_message_breakeven() -> None:
    data = PositionEventData(
        event="breakeven",
        trade_id="journal-123",
        market="XAUUSD",
        reason="Цена прошла 1.0R, стоп переведён в безубыток",
        new_stop_loss=2000.0,
        current_price=2010.0,
    )

    text = format_position_event_message(data)

    assert "⚖️ Безубыток" in text
    assert "XAUUSD" in text
    assert "Цена: 2010.00" in text
    assert "Новый стоп: 2000.00" in text
    assert "Цена прошла 1.0R, стоп переведён в безубыток" in text
    assert "journal-123" in text


def test_format_position_event_message_scale_in_with_volume_change() -> None:
    data = PositionEventData(
        event="scale_in",
        trade_id="journal-123",
        market="XAUUSD",
        reason="Уверенность выросла, риск в норме",
        volume_change=0.5,
    )

    text = format_position_event_message(data)

    assert "➕ Добавили объём" in text
    assert "Изменение объёма: +0.5000" in text


def test_format_position_event_message_scale_out_with_negative_volume() -> None:
    data = PositionEventData(
        event="scale_out",
        trade_id="journal-123",
        market="XAUUSD",
        reason="Уверенность снизилась",
        volume_change=-0.3,
    )

    text = format_position_event_message(data)

    assert "➖ Уменьшили объём" in text
    assert "Изменение объёма: -0.3000" in text


def test_format_position_event_message_omits_absent_optional_fields() -> None:
    data = PositionEventData(
        event="partial_close",
        trade_id="journal-123",
        market="XAUUSD",
        reason="Снизили риск перед новостями",
    )

    text = format_position_event_message(data)

    assert "✂️ Частичное закрытие" in text
    assert "Цена:" not in text
    assert "Новый стоп:" not in text
    assert "Изменение объёма:" not in text


def test_format_position_event_message_raises_for_unknown_event() -> None:
    data = PositionEventData(
        event="not_a_real_event", trade_id="journal-123", market="XAUUSD", reason="x"
    )

    with pytest.raises(KeyError):
        format_position_event_message(data)


def _trade(**overrides: object) -> Trade:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "symbol_id": _SYMBOL_ID,
        "direction": "buy",
        "status": "closed",
        "volume": 1.0,
        "entry_price": 2000.0,
        "stop_loss": 1990.0,
        "take_profit": 2020.0,
        "exit_price": 2020.0,
        "magic_number": 42,
        "realized_pnl": 20.0,
    }
    defaults.update(overrides)
    return Trade(**defaults)


def test_format_trade_closed_message_raises_without_prices() -> None:
    with pytest.raises(ValueError, match="entry_price"):
        format_trade_closed_message(_trade(entry_price=None))


def test_format_trade_closed_message_labels_profit_and_take_profit_hit() -> None:
    trade = _trade()

    text = format_trade_closed_message(trade)

    assert "✅ Профит +20.00$" in text
    assert "BUY" in text
    assert "Тейк-профит достигнут" in text
    assert str(trade.id) in text


def test_format_trade_closed_message_labels_loss_and_stop_loss_hit() -> None:
    trade = _trade(exit_price=1990.0, realized_pnl=-15.0)

    text = format_trade_closed_message(trade)

    assert "❌ Убыток -15.00$" in text
    assert "Сработал стоп-лосс" in text


def test_format_trade_closed_message_falls_back_to_a_neutral_reason() -> None:
    trade = _trade(exit_price=2005.0)

    text = format_trade_closed_message(trade)

    assert "Закрыта по рыночному сигналу" in text


def test_format_trade_closed_message_includes_prediction_accuracy_when_given() -> None:
    trade = _trade()

    text = format_trade_closed_message(trade, prediction_accuracy="Точность высокая")

    assert "Точность высокая" in text


def _post_mortem_report(**overrides: object) -> PostMortemReport:
    defaults: dict[str, object] = {
        "trade_id": "trade-123",
        "review": TradeReview(
            trade_id="trade-123",
            is_win=False,
            realized_return_pct=-0.5,
            risk_pct=0.5,
            r_multiple=-1.0,
            holding_time=None,
        ),
        "disagreeing_departments": [],
        "missing_departments": [],
        "should_have_been_skipped": False,
        "would_repeat": True,
    }
    defaults.update(overrides)
    return PostMortemReport(**defaults)  # type: ignore[arg-type]


def test_format_post_mortem_message_includes_key_fields() -> None:
    report = _post_mortem_report(
        disagreeing_departments=["macro", "news"],
        missing_departments=["order_flow"],
        should_have_been_skipped=True,
        would_repeat=False,
    )

    text = format_post_mortem_message(report, market="XAUUSD")

    assert "🔍 Разбор сделки — XAUUSD" in text
    assert "-1.00R" in text
    assert "Открыли бы снова: НЕТ" in text
    assert "Были против: Макро, Новости" in text
    assert "Не хватало данных: Order Flow" in text
    assert "trade-123" in text


def test_format_post_mortem_message_omits_absent_sections() -> None:
    report = _post_mortem_report()

    text = format_post_mortem_message(report, market="XAUUSD")

    assert "Были против" not in text
    assert "Не хватало данных" not in text
    assert "Оказались правы" not in text
    assert "Ошиблись" not in text
    assert "Открыли бы снова: ДА" in text


def test_format_post_mortem_message_includes_department_correctness() -> None:
    report = _post_mortem_report(
        department_correctness={"technical": True, "macro": False},
    )

    text = format_post_mortem_message(report, market="XAUUSD")

    assert "Оказались правы: Технический анализ" in text
    assert "Ошиблись: Макро" in text


def _pre_close_assessment(**overrides: object) -> PositionPreCloseAssessment:
    defaults: dict[str, object] = {
        "trade_id": "trade-456",
        "market": "XAUUSD",
        "recommendation": "keep",
        "confidence_pct": 82.0,
        "reasons": ["current_decision_agrees:BUY@82%"],
        "weekend_risk": None,
    }
    defaults.update(overrides)
    return PositionPreCloseAssessment(**defaults)  # type: ignore[arg-type]


def test_format_pre_close_report_message_includes_key_fields() -> None:
    assessment = _pre_close_assessment(
        recommendation="close",
        reasons=["current_decision_opposes:SELL@75%"],
        weekend_risk="Elevated weekend gap risk: current regime is 'high_volatility'.",
    )

    text = format_pre_close_report_message(assessment)

    assert "🌙 Перед закрытием рынка — XAUUSD" in text
    assert "Рекомендация: ЗАКРЫТЬ" in text
    assert "Уверенность: 82%" in text
    assert "Сигнал против, за SELL 75%" in text
    assert "⚠️ Повышенный риск гэпа на выходных" in text
    assert "trade-456" in text


def test_format_pre_close_report_message_translates_the_agrees_tag() -> None:
    assessment = _pre_close_assessment(reasons=["current_decision_agrees:BUY@82%"])

    text = format_pre_close_report_message(assessment)

    assert "Сигнал подтверждает BUY 82%" in text


def test_format_pre_close_report_message_translates_known_short_tags() -> None:
    assessment = _pre_close_assessment(
        reasons=["no_strong_directional_signal_this_cycle", "position_in_profit"]
    )

    text = format_pre_close_report_message(assessment)

    assert "Нет сильного сигнала" in text
    assert "Позиция в плюсе" in text


def test_format_pre_close_report_message_omits_weekend_risk_when_absent() -> None:
    assessment = _pre_close_assessment(weekend_risk=None)

    text = format_pre_close_report_message(assessment)

    assert "риск гэпа" not in text.lower()


def test_format_pre_close_report_message_notes_low_weekend_risk() -> None:
    assessment = _pre_close_assessment(
        weekend_risk="No elevated weekend gap risk signal from the current regime ('range')."
    )

    text = format_pre_close_report_message(assessment)

    assert "Риск гэпа на выходных: низкий" in text


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
    assert "Сигналов: 10" in text
    assert "Сделок: 5" in text
    assert "винрейт 60%" in text
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

    assert "не определена" in text


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
    assert "Восстановлено автоматически: да" in text
    assert "Нужно вмешательство: нет" in text
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


def _wait_decision(**overrides: object) -> ChiefAIDecision:
    defaults: dict[str, object] = {
        "state": "WAIT",
        "probability": ProbabilityEstimate(
            bullish_probability=0.3, bearish_probability=0.5, neutral_probability=0.2
        ),
        "confidence_pct": 58.0,
        "uncertainty_factors": [],
        "reasons": [],
        "reduced_confidence_factors": [],
        "trade_quality": TradeQualityResult(score=63.0, risk_score=40.0),
    }
    defaults.update(overrides)
    return ChiefAIDecision(**defaults)  # type: ignore[arg-type]


def test_build_no_trade_reasons_ru_translates_known_codes() -> None:
    decision = _wait_decision(
        reasons=["risk_rejected:confidence_level_not_executable: low"],
        reduced_confidence_factors=["reduced_confidence:news_unavailable"],
    )

    reasons = build_no_trade_reasons_ru(decision, {})

    assert any("Недостаточная уверенность" in reason for reason in reasons)
    assert "Нет данных по новостям" in reasons


def test_build_no_trade_reasons_ru_includes_department_disagreement_tags() -> None:
    decision = _wait_decision(reasons=["conflicting_departments"])
    votes: dict[str, dict[str, float | str]] = {
        "technical": {"bias": "bullish", "confidence": 0.7},
        "correlation": {"bias": "bearish", "confidence": 0.6},
    }

    reasons = build_no_trade_reasons_ru(decision, votes)

    assert "Департаменты дают противоречивые сигналы" in reasons
    assert "Технический анализ ↑" in reasons
    assert "Корреляция ↓" in reasons


def test_build_no_trade_reasons_ru_falls_back_to_the_raw_code_when_unknown() -> None:
    decision = _wait_decision(reasons=["some_new_reason_code"])

    reasons = build_no_trade_reasons_ru(decision, {})

    assert "some_new_reason_code" in reasons


def test_format_no_trade_message_includes_quality_confidence_and_reasons() -> None:
    data = NoTradeMessageData(
        market="XAUUSD",
        quality_score=63.0,
        confidence_pct=58.0,
        reasons=["DXY против тренда", "Слабый импульс"],
        next_scan_minutes=2.0,
    )

    text = format_no_trade_message(data)

    assert "❌ Нет сделки — XAUUSD" in text
    assert "63/100" in text
    assert "58%" in text
    assert "• DXY против тренда" in text
    assert "• Слабый импульс" in text
    assert "через 2 мин." in text


def test_format_no_trade_message_omits_reasons_block_when_empty() -> None:
    data = NoTradeMessageData(
        market="XAUUSD", quality_score=50.0, confidence_pct=40.0, next_scan_minutes=1.0
    )

    text = format_no_trade_message(data)

    assert "Причины" not in text
