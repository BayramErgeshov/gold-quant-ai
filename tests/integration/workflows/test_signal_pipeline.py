"""Integration tests for the Signal Workflow (WORKFLOW_ENGINE.md)."""

from __future__ import annotations

import dataclasses

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.execution.mt5_client import (
    AccountInfo,
    MT5Client,
    OpenPosition,
    OrderBookSnapshot,
    OrderRequest,
    OrderResult,
    SymbolTick,
)
from src.core.execution.order_validation import ExecutionValidationRequest
from src.core.notifications.telegram_client import TelegramNotifier
from src.engines.chief_ai.decision import ChiefAIDecision
from src.engines.risk_engine.position_sizing import PositionSizeResult
from src.engines.statistics_engine.probability import ProbabilityEstimate
from src.models.symbol import Symbol
from src.repositories.symbol_repository import SymbolRepository
from src.repositories.trade_repository import TradeRepository
from src.workflows.trade.pipeline import SignalWorkflow, SignalWorkflowInput

pytestmark = pytest.mark.asyncio


class _FakeMT5Client(MT5Client):
    def __init__(self, *, place_order_result: OrderResult) -> None:
        self.place_order_result = place_order_result
        self.last_order_request: OrderRequest | None = None

    async def connect(self) -> bool:
        return True

    async def is_connected(self) -> bool:
        return True

    async def get_account_info(self) -> AccountInfo:
        raise NotImplementedError

    async def place_order(self, request: OrderRequest) -> OrderResult:
        self.last_order_request = request
        return self.place_order_result

    async def modify_order(
        self,
        broker_ticket: str,
        *,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> OrderResult:
        raise NotImplementedError

    async def close_position(
        self, broker_ticket: str, *, volume: float | None = None
    ) -> OrderResult:
        raise NotImplementedError

    async def cancel_order(self, broker_ticket: str) -> OrderResult:
        raise NotImplementedError

    async def get_candles(self, symbol: str, timeframe: str, count: int) -> list[dict[str, object]]:
        raise NotImplementedError

    async def get_symbol_tick(self, symbol: str) -> SymbolTick:
        raise NotImplementedError

    async def get_order_book(self, symbol: str) -> OrderBookSnapshot | None:
        return None

    async def get_open_positions(
        self, *, symbol: str | None = None, magic_number: int | None = None
    ) -> list[OpenPosition]:
        raise NotImplementedError


class _FakeTelegramNotifier(TelegramNotifier):
    def __init__(self, *, send_result: bool = True) -> None:
        self.send_result = send_result
        self.sent_messages: list[tuple[str, str]] = []

    async def send_message(self, chat_id: str, text: str) -> bool:
        self.sent_messages.append((chat_id, text))
        return self.send_result


def _decision(state: str) -> ChiefAIDecision:
    return ChiefAIDecision(
        state=state,  # type: ignore[arg-type]
        probability=ProbabilityEstimate(
            bullish_probability=0.8, bearish_probability=0.1, neutral_probability=0.1
        ),
        confidence_pct=82.0,
        uncertainty_factors=[],
        reasons=["bullish_probability_exceeds_bearish"],
        supporting_evidence=["structure_bullish"],
        opposing_evidence=[],
    )


def _approved_execution_request(*, market_symbol_name: str) -> ExecutionValidationRequest:
    return ExecutionValidationRequest(
        expected_symbol=market_symbol_name,
        order_symbol=market_symbol_name,
        expected_account="12345",
        actual_account="12345",
        account_type="demo",
        live_trading_approved=False,
        is_terminal_connected=True,
        is_market_open=True,
        risk_approved=True,
        chief_ai_approved=True,
    )


async def _make_symbol(session: AsyncSession) -> Symbol:
    return await SymbolRepository(session).add(Symbol(name="XAUUSD", display_name="Gold"))


async def test_non_actionable_decision_never_reaches_mt5_or_telegram(
    session: AsyncSession,
) -> None:
    symbol = await _make_symbol(session)
    mt5 = _FakeMT5Client(
        place_order_result=OrderResult(success=True, broker_ticket="1", filled_price=2000.0)
    )
    telegram = _FakeTelegramNotifier()
    workflow = SignalWorkflow(
        trade_repository=TradeRepository(session), mt5_client=mt5, telegram_notifier=telegram
    )
    workflow_input = SignalWorkflowInput(
        symbol_id=symbol.id,
        market_symbol_name="XAUUSD",
        entry_price=2000.0,
        stop_loss=1990.0,
        take_profit=2020.0,
        position_size=PositionSizeResult(
            position_size_units=1.0, risk_amount=100.0, effective_risk_pct=1.0
        ),
        execution_request=_approved_execution_request(market_symbol_name="XAUUSD"),
        strategy_name="xauusd_h1_trend",
        strategy_version="1.0.0",
        telegram_chat_id="chat-1",
    )

    result = await workflow.run(_decision("WAIT"), workflow_input)

    assert result.executed is False
    assert result.trade is None
    assert "decision_not_actionable" in result.rejection_reasons[0]
    assert mt5.last_order_request is None
    assert telegram.sent_messages == []


async def test_execution_validation_failure_prevents_trade_creation(
    session: AsyncSession,
) -> None:
    symbol = await _make_symbol(session)
    mt5 = _FakeMT5Client(
        place_order_result=OrderResult(success=True, broker_ticket="1", filled_price=2000.0)
    )
    telegram = _FakeTelegramNotifier()
    workflow = SignalWorkflow(
        trade_repository=TradeRepository(session), mt5_client=mt5, telegram_notifier=telegram
    )
    execution_request = dataclasses.replace(
        _approved_execution_request(market_symbol_name="XAUUSD"), is_market_open=False
    )
    workflow_input = SignalWorkflowInput(
        symbol_id=symbol.id,
        market_symbol_name="XAUUSD",
        entry_price=2000.0,
        stop_loss=1990.0,
        take_profit=2020.0,
        position_size=PositionSizeResult(
            position_size_units=1.0, risk_amount=100.0, effective_risk_pct=1.0
        ),
        execution_request=execution_request,
        strategy_name="xauusd_h1_trend",
        strategy_version="1.0.0",
        telegram_chat_id="chat-1",
    )

    result = await workflow.run(_decision("BUY"), workflow_input)

    assert result.executed is False
    assert result.trade is None
    assert "market_closed" in result.rejection_reasons
    assert mt5.last_order_request is None


async def test_mt5_rejection_journals_a_rejected_trade(session: AsyncSession) -> None:
    symbol = await _make_symbol(session)
    mt5 = _FakeMT5Client(
        place_order_result=OrderResult(
            success=False, broker_ticket=None, filled_price=None, error_message="requote"
        )
    )
    telegram = _FakeTelegramNotifier()
    workflow = SignalWorkflow(
        trade_repository=TradeRepository(session), mt5_client=mt5, telegram_notifier=telegram
    )
    workflow_input = SignalWorkflowInput(
        symbol_id=symbol.id,
        market_symbol_name="XAUUSD",
        entry_price=2000.0,
        stop_loss=1990.0,
        take_profit=2020.0,
        position_size=PositionSizeResult(
            position_size_units=1.0, risk_amount=100.0, effective_risk_pct=1.0
        ),
        execution_request=_approved_execution_request(market_symbol_name="XAUUSD"),
        strategy_name="xauusd_h1_trend",
        strategy_version="1.0.0",
        telegram_chat_id="chat-1",
    )

    result = await workflow.run(_decision("BUY"), workflow_input)

    assert result.executed is False
    assert result.trade is not None
    assert result.trade.status == "rejected"
    assert result.trade.error_message == "requote"
    assert result.rejection_reasons == ["requote"]
    assert telegram.sent_messages == []


async def test_successful_buy_journals_open_trade_and_sends_telegram_preview(
    session: AsyncSession,
) -> None:
    symbol = await _make_symbol(session)
    mt5 = _FakeMT5Client(
        place_order_result=OrderResult(success=True, broker_ticket="9001", filled_price=2000.0)
    )
    telegram = _FakeTelegramNotifier()
    workflow = SignalWorkflow(
        trade_repository=TradeRepository(session), mt5_client=mt5, telegram_notifier=telegram
    )
    workflow_input = SignalWorkflowInput(
        symbol_id=symbol.id,
        market_symbol_name="XAUUSD",
        entry_price=2000.0,
        stop_loss=1990.0,
        take_profit=2020.0,
        position_size=PositionSizeResult(
            position_size_units=1.0, risk_amount=100.0, effective_risk_pct=1.0
        ),
        execution_request=_approved_execution_request(market_symbol_name="XAUUSD"),
        strategy_name="xauusd_h1_trend",
        strategy_version="1.0.0",
        telegram_chat_id="chat-1",
    )

    result = await workflow.run(_decision("BUY"), workflow_input)

    assert result.executed is True
    assert result.trade is not None
    assert result.trade.status == "open"
    assert result.trade.broker_ticket == "9001"
    assert result.trade.opened_at is not None
    assert result.telegram_sent is True
    assert len(telegram.sent_messages) == 1
    assert telegram.sent_messages[0][0] == "chat-1"
    assert "XAUUSD" in telegram.sent_messages[0][1]

    stored = await TradeRepository(session).get_by_broker_ticket("9001")
    assert stored is not None
    assert stored.status == "open"


async def test_successful_buy_persists_reasons_and_scenario_plan(
    session: AsyncSession,
) -> None:
    # Per the "Strategy Explanation" production requirement: Reasons and
    # Expected Scenario must survive beyond the one-shot Telegram preview.
    symbol = await _make_symbol(session)
    mt5 = _FakeMT5Client(
        place_order_result=OrderResult(success=True, broker_ticket="9010", filled_price=2000.0)
    )
    workflow = SignalWorkflow(
        trade_repository=TradeRepository(session),
        mt5_client=mt5,
        telegram_notifier=_FakeTelegramNotifier(),
    )
    workflow_input = SignalWorkflowInput(
        symbol_id=symbol.id,
        market_symbol_name="XAUUSD",
        entry_price=2000.0,
        stop_loss=1990.0,
        take_profit=2020.0,
        position_size=PositionSizeResult(
            position_size_units=1.0, risk_amount=100.0, effective_risk_pct=1.0
        ),
        execution_request=_approved_execution_request(market_symbol_name="XAUUSD"),
        strategy_name="xauusd_h1_trend",
        strategy_version="1.0.0",
        telegram_chat_id="chat-1",
    )

    result = await workflow.run(_decision("BUY"), workflow_input)

    assert result.trade is not None
    assert result.trade.reasons == ["bullish_probability_exceeds_bearish"]
    assert result.trade.scenario_plan is not None
    assert "continues higher" in result.trade.scenario_plan["primary_scenario"]
    assert result.trade.scenario_plan["alternative_scenario"]
    assert result.trade.scenario_plan["invalidation"]


async def test_telegram_message_includes_target_and_department_reason_tags(
    session: AsyncSession,
) -> None:
    symbol = await _make_symbol(session)
    mt5 = _FakeMT5Client(
        place_order_result=OrderResult(success=True, broker_ticket="9003", filled_price=2000.0)
    )
    telegram = _FakeTelegramNotifier()
    workflow = SignalWorkflow(
        trade_repository=TradeRepository(session), mt5_client=mt5, telegram_notifier=telegram
    )
    workflow_input = SignalWorkflowInput(
        symbol_id=symbol.id,
        market_symbol_name="XAUUSD",
        entry_price=2000.0,
        stop_loss=1990.0,
        take_profit=2030.0,
        position_size=PositionSizeResult(
            position_size_units=1.0, risk_amount=100.0, effective_risk_pct=1.0
        ),
        execution_request=_approved_execution_request(market_symbol_name="XAUUSD"),
        strategy_name="xauusd_h1_trend",
        strategy_version="1.0.0",
        telegram_chat_id="chat-1",
        department_votes={
            "technical": {"bias": "bullish", "confidence": 0.8},
            "correlation": {"bias": "bullish", "confidence": 0.6},
            "order_flow": {"bias": "bearish", "confidence": 0.3},
        },
        market_regime="bull_trend",
    )

    await workflow.run(_decision("BUY"), workflow_input)

    message = telegram.sent_messages[0][1]
    assert "🎯 TP:\n2030.00" in message
    assert "✅ Технический анализ" in message
    assert "✅ Корреляция" in message
    assert "❌ Order Flow" in message


async def test_telegram_message_omits_target_and_reason_block_without_a_target(
    session: AsyncSession,
) -> None:
    symbol = await _make_symbol(session)
    mt5 = _FakeMT5Client(
        place_order_result=OrderResult(success=True, broker_ticket="9004", filled_price=2000.0)
    )
    telegram = _FakeTelegramNotifier()
    workflow = SignalWorkflow(
        trade_repository=TradeRepository(session), mt5_client=mt5, telegram_notifier=telegram
    )
    workflow_input = SignalWorkflowInput(
        symbol_id=symbol.id,
        market_symbol_name="XAUUSD",
        entry_price=2000.0,
        stop_loss=1990.0,
        take_profit=None,
        position_size=PositionSizeResult(
            position_size_units=1.0, risk_amount=100.0, effective_risk_pct=1.0
        ),
        execution_request=_approved_execution_request(market_symbol_name="XAUUSD"),
        strategy_name="xauusd_h1_trend",
        strategy_version="1.0.0",
        telegram_chat_id="chat-1",
    )

    await workflow.run(_decision("BUY"), workflow_input)

    message = telegram.sent_messages[0][1]
    assert "🎯" not in message
    assert "📌 Причины:" not in message


async def test_sell_decision_uses_sell_direction(session: AsyncSession) -> None:
    symbol = await _make_symbol(session)
    mt5 = _FakeMT5Client(
        place_order_result=OrderResult(success=True, broker_ticket="9002", filled_price=2000.0)
    )
    telegram = _FakeTelegramNotifier()
    workflow = SignalWorkflow(
        trade_repository=TradeRepository(session), mt5_client=mt5, telegram_notifier=telegram
    )
    workflow_input = SignalWorkflowInput(
        symbol_id=symbol.id,
        market_symbol_name="XAUUSD",
        entry_price=2000.0,
        stop_loss=2010.0,
        take_profit=1980.0,
        position_size=PositionSizeResult(
            position_size_units=1.0, risk_amount=100.0, effective_risk_pct=1.0
        ),
        execution_request=_approved_execution_request(market_symbol_name="XAUUSD"),
        strategy_name="xauusd_h1_trend",
        strategy_version="1.0.0",
        telegram_chat_id="chat-1",
    )

    result = await workflow.run(_decision("SELL"), workflow_input)

    assert result.trade is not None
    assert result.trade.direction == "sell"
    assert mt5.last_order_request is not None
    assert mt5.last_order_request.order_type == "sell"


async def test_journals_market_regime_and_confidence_at_signal_time(
    session: AsyncSession,
) -> None:
    symbol = await _make_symbol(session)
    mt5 = _FakeMT5Client(
        place_order_result=OrderResult(success=True, broker_ticket="9005", filled_price=2000.0)
    )
    telegram = _FakeTelegramNotifier()
    workflow = SignalWorkflow(
        trade_repository=TradeRepository(session), mt5_client=mt5, telegram_notifier=telegram
    )
    workflow_input = SignalWorkflowInput(
        symbol_id=symbol.id,
        market_symbol_name="XAUUSD",
        entry_price=2000.0,
        stop_loss=1990.0,
        take_profit=2030.0,
        position_size=PositionSizeResult(
            position_size_units=1.0, risk_amount=100.0, effective_risk_pct=1.0
        ),
        execution_request=_approved_execution_request(market_symbol_name="XAUUSD"),
        strategy_name="xauusd_h1_trend",
        strategy_version="1.0.0",
        telegram_chat_id="chat-1",
        market_regime="bull_trend",
    )

    result = await workflow.run(_decision("BUY"), workflow_input)

    assert result.trade is not None
    assert result.trade.market_regime == "bull_trend"
    assert result.trade.confidence_pct == 82.0
