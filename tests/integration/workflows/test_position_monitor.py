"""Integration tests for the Trade Monitoring Workflow (`PositionMonitor`)."""

from __future__ import annotations

from datetime import UTC, datetime

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
from src.core.notifications.telegram_client import TelegramNotifier
from src.engines.learning_engine.post_mortem import PostMortemService
from src.engines.risk_engine.dynamic_stop import DynamicStopInputs
from src.models.symbol import Symbol
from src.models.trade import Trade
from src.repositories.improvement_proposal_repository import ImprovementProposalRepository
from src.repositories.symbol_repository import SymbolRepository
from src.repositories.trade_repository import TradeRepository
from src.workflows.execution.position_monitor import PositionMonitor


class _FakeTelegramNotifier(TelegramNotifier):
    def __init__(self) -> None:
        self.sent_messages: list[tuple[str, str]] = []

    async def send_message(self, chat_id: str, text: str) -> bool:
        self.sent_messages.append((chat_id, text))
        return True


pytestmark = pytest.mark.asyncio


class _FakeMT5Client(MT5Client):
    def __init__(
        self,
        *,
        positions: list[OpenPosition],
        modify_result: OrderResult | None = None,
        tick: SymbolTick | None = None,
    ) -> None:
        self._positions = positions
        self.modify_result = modify_result or OrderResult(
            success=True, broker_ticket=None, filled_price=None
        )
        self.modify_calls: list[tuple[str, float | None, float | None]] = []
        self._tick = tick

    async def connect(self) -> bool:
        return True

    async def is_connected(self) -> bool:
        return True

    async def get_account_info(self) -> AccountInfo:
        raise NotImplementedError

    async def place_order(self, request: OrderRequest) -> OrderResult:
        raise NotImplementedError

    async def modify_order(
        self,
        broker_ticket: str,
        *,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> OrderResult:
        self.modify_calls.append((broker_ticket, stop_loss, take_profit))
        return self.modify_result

    async def close_position(
        self, broker_ticket: str, *, volume: float | None = None
    ) -> OrderResult:
        raise NotImplementedError

    async def cancel_order(self, broker_ticket: str) -> OrderResult:
        raise NotImplementedError

    async def get_candles(self, symbol: str, timeframe: str, count: int) -> list[dict[str, object]]:
        raise NotImplementedError

    async def get_symbol_tick(self, symbol: str) -> SymbolTick:
        if self._tick is None:
            raise NotImplementedError
        return self._tick

    async def get_order_book(self, symbol: str) -> OrderBookSnapshot | None:
        return None

    async def get_open_positions(
        self, *, symbol: str | None = None, magic_number: int | None = None
    ) -> list[OpenPosition]:
        return self._positions


def _open_position(*, ticket: str, direction: str, current_price: float) -> OpenPosition:
    return OpenPosition(
        ticket=ticket,
        symbol="XAUUSD",
        direction=direction,  # type: ignore[arg-type]
        volume=1.0,
        entry_price=2000.0,
        stop_loss=1990.0,
        take_profit=2020.0,
        current_price=current_price,
        profit=0.0,
        magic_number=42,
        opened_at=datetime.now(UTC),
    )


async def _make_symbol(session: AsyncSession) -> Symbol:
    return await SymbolRepository(session).add(Symbol(name="XAUUSD", display_name="Gold"))


async def _make_open_trade(
    session: AsyncSession,
    symbol: Symbol,
    *,
    broker_ticket: str,
    entry_price: float,
    initial_stop_loss: float,
    direction: str = "buy",
) -> Trade:
    trade = Trade(
        symbol_id=symbol.id,
        direction=direction,
        status="open",
        volume=1.0,
        entry_price=entry_price,
        stop_loss=initial_stop_loss,
        initial_stop_loss=initial_stop_loss,
        take_profit=entry_price + 20.0,
        magic_number=42,
        broker_ticket=broker_ticket,
    )
    return await TradeRepository(session).add(trade)


async def test_moves_stop_to_breakeven_once_trigger_reached(session: AsyncSession) -> None:
    symbol = await _make_symbol(session)
    await _make_open_trade(
        session, symbol, broker_ticket="9001", entry_price=2000.0, initial_stop_loss=1990.0
    )
    # 1R risk distance is 10.0; moved +10.0 in favor meets a 1.0 R trigger.
    mt5 = _FakeMT5Client(
        positions=[_open_position(ticket="9001", direction="buy", current_price=2010.0)]
    )
    monitor = PositionMonitor(mt5_client=mt5, trade_repository=TradeRepository(session))

    result = await monitor.run_cycle(mt5_symbol="XAUUSD", magic_number=42)

    assert result.moved_to_breakeven == ["9001"]
    assert mt5.modify_calls == [("9001", 2000.0, None)]
    stored = await TradeRepository(session).get_by_broker_ticket("9001")
    assert stored is not None
    assert stored.breakeven_moved is True
    assert stored.stop_loss == 2000.0


async def test_sends_a_telegram_notification_when_moved_to_breakeven(
    session: AsyncSession,
) -> None:
    symbol = await _make_symbol(session)
    await _make_open_trade(
        session, symbol, broker_ticket="9010", entry_price=2000.0, initial_stop_loss=1990.0
    )
    mt5 = _FakeMT5Client(
        positions=[_open_position(ticket="9010", direction="buy", current_price=2010.0)]
    )
    telegram = _FakeTelegramNotifier()
    monitor = PositionMonitor(
        mt5_client=mt5,
        trade_repository=TradeRepository(session),
        telegram_notifier=telegram,
        telegram_chat_id="chat-1",
    )

    await monitor.run_cycle(mt5_symbol="XAUUSD", magic_number=42)

    assert len(telegram.sent_messages) == 1
    chat_id, message = telegram.sent_messages[0]
    assert chat_id == "chat-1"
    assert "⚖️ Безубыток" in message
    assert "XAUUSD" in message


async def test_does_not_send_telegram_notification_when_not_configured(
    session: AsyncSession,
) -> None:
    symbol = await _make_symbol(session)
    await _make_open_trade(
        session, symbol, broker_ticket="9011", entry_price=2000.0, initial_stop_loss=1990.0
    )
    mt5 = _FakeMT5Client(
        positions=[_open_position(ticket="9011", direction="buy", current_price=2010.0)]
    )
    monitor = PositionMonitor(mt5_client=mt5, trade_repository=TradeRepository(session))

    result = await monitor.run_cycle(mt5_symbol="XAUUSD", magic_number=42)

    assert result.moved_to_breakeven == ["9011"]  # unaffected by the absent notifier


async def test_does_not_move_stop_before_trigger_reached(session: AsyncSession) -> None:
    symbol = await _make_symbol(session)
    await _make_open_trade(
        session, symbol, broker_ticket="9002", entry_price=2000.0, initial_stop_loss=1990.0
    )
    mt5 = _FakeMT5Client(
        positions=[_open_position(ticket="9002", direction="buy", current_price=2005.0)]
    )
    monitor = PositionMonitor(mt5_client=mt5, trade_repository=TradeRepository(session))

    result = await monitor.run_cycle(mt5_symbol="XAUUSD", magic_number=42)

    assert result.moved_to_breakeven == []
    assert mt5.modify_calls == []


async def test_sell_direction_computes_favorable_move_correctly(session: AsyncSession) -> None:
    symbol = await _make_symbol(session)
    await _make_open_trade(
        session,
        symbol,
        broker_ticket="9003",
        entry_price=2000.0,
        initial_stop_loss=2010.0,
        direction="sell",
    )
    mt5 = _FakeMT5Client(
        positions=[_open_position(ticket="9003", direction="sell", current_price=1990.0)]
    )
    monitor = PositionMonitor(mt5_client=mt5, trade_repository=TradeRepository(session))

    result = await monitor.run_cycle(mt5_symbol="XAUUSD", magic_number=42)

    assert result.moved_to_breakeven == ["9003"]
    assert mt5.modify_calls == [("9003", 2000.0, None)]


async def test_skips_positions_already_moved_to_breakeven(session: AsyncSession) -> None:
    symbol = await _make_symbol(session)
    trade = await _make_open_trade(
        session, symbol, broker_ticket="9004", entry_price=2000.0, initial_stop_loss=1990.0
    )
    trade.breakeven_moved = True
    await TradeRepository(session).add(trade)
    mt5 = _FakeMT5Client(
        positions=[_open_position(ticket="9004", direction="buy", current_price=2050.0)]
    )
    monitor = PositionMonitor(mt5_client=mt5, trade_repository=TradeRepository(session))

    result = await monitor.run_cycle(mt5_symbol="XAUUSD", magic_number=42)

    assert result.moved_to_breakeven == []
    assert mt5.modify_calls == []


async def test_skips_positions_with_no_matching_journal_entry(session: AsyncSession) -> None:
    mt5 = _FakeMT5Client(
        positions=[_open_position(ticket="unknown", direction="buy", current_price=2050.0)]
    )
    monitor = PositionMonitor(mt5_client=mt5, trade_repository=TradeRepository(session))

    result = await monitor.run_cycle(mt5_symbol="XAUUSD", magic_number=42)

    assert result.checked == 1
    assert result.moved_to_breakeven == []


async def test_records_error_when_modify_order_fails(session: AsyncSession) -> None:
    symbol = await _make_symbol(session)
    await _make_open_trade(
        session, symbol, broker_ticket="9005", entry_price=2000.0, initial_stop_loss=1990.0
    )
    mt5 = _FakeMT5Client(
        positions=[_open_position(ticket="9005", direction="buy", current_price=2015.0)],
        modify_result=OrderResult(
            success=False, broker_ticket=None, filled_price=None, error_message="requote"
        ),
    )
    monitor = PositionMonitor(mt5_client=mt5, trade_repository=TradeRepository(session))

    result = await monitor.run_cycle(mt5_symbol="XAUUSD", magic_number=42)

    assert result.moved_to_breakeven == []
    assert result.errors == ["9005: requote"]


async def test_skips_trade_with_zero_risk_distance(session: AsyncSession) -> None:
    symbol = await _make_symbol(session)
    # A degenerate journal entry where the stop was never distinct from
    # entry: there is no risk distance to measure an R-multiple against.
    await _make_open_trade(
        session, symbol, broker_ticket="9006", entry_price=2000.0, initial_stop_loss=2000.0
    )
    mt5 = _FakeMT5Client(
        positions=[_open_position(ticket="9006", direction="buy", current_price=2050.0)]
    )
    monitor = PositionMonitor(mt5_client=mt5, trade_repository=TradeRepository(session))

    result = await monitor.run_cycle(mt5_symbol="XAUUSD", magic_number=42)

    assert result.moved_to_breakeven == []
    assert mt5.modify_calls == []


async def test_reconciles_a_position_no_longer_open_at_broker_as_closed(
    session: AsyncSession,
) -> None:
    symbol = await _make_symbol(session)
    trade = await _make_open_trade(
        session, symbol, broker_ticket="9020", entry_price=2000.0, initial_stop_loss=1990.0
    )
    mt5 = _FakeMT5Client(
        positions=[], tick=SymbolTick(bid=1985.0, ask=1985.5, timestamp=datetime.now(UTC))
    )
    monitor = PositionMonitor(mt5_client=mt5, trade_repository=TradeRepository(session))

    result = await monitor.run_cycle(mt5_symbol="XAUUSD", magic_number=42)

    assert result.closed_trades == [str(trade.id)]
    stored = await TradeRepository(session).get_by_broker_ticket("9020")
    assert stored is not None
    assert stored.status == "closed"
    assert stored.exit_price == 1985.0
    assert stored.realized_pnl == pytest.approx(-15.0)


async def test_does_not_reconcile_positions_still_open_at_broker(
    session: AsyncSession,
) -> None:
    symbol = await _make_symbol(session)
    await _make_open_trade(
        session, symbol, broker_ticket="9021", entry_price=2000.0, initial_stop_loss=1990.0
    )
    mt5 = _FakeMT5Client(
        positions=[_open_position(ticket="9021", direction="buy", current_price=2005.0)]
    )
    monitor = PositionMonitor(mt5_client=mt5, trade_repository=TradeRepository(session))

    result = await monitor.run_cycle(mt5_symbol="XAUUSD", magic_number=42)

    assert result.closed_trades == []


class _GlitchThenPresentMT5Client(_FakeMT5Client):
    """Returns an empty position list on the first call, then the real
    (still-open) positions on every call after -- simulates the
    transient IPC glitch a production incident traced a false
    reconciliation to: one cycle's `get_open_positions()` read came back
    empty while the position was genuinely still open on the broker.
    """

    def __init__(self, *, real_positions: list[OpenPosition], **kwargs: object) -> None:
        super().__init__(positions=[], **kwargs)  # type: ignore[arg-type]
        self._real_positions = real_positions
        self._calls = 0

    async def get_open_positions(
        self, *, symbol: str | None = None, magic_number: int | None = None
    ) -> list[OpenPosition]:
        self._calls += 1
        return [] if self._calls == 1 else self._real_positions


async def test_a_single_transient_empty_read_does_not_falsely_reconcile_an_open_position(
    session: AsyncSession,
) -> None:
    """Regression test for a production incident: a position that was
    genuinely still open got journaled as "closed" after about a
    minute, repeatedly -- traced to a single transient
    `get_open_positions()` read coming back empty (not `None`, so the
    client's own None-only retry never caught it) while the position
    was, in reality, still open. The very next, immediate re-check
    inside reconciliation must catch this before acting on it.
    """
    symbol = await _make_symbol(session)
    trade = await _make_open_trade(
        session, symbol, broker_ticket="9022", entry_price=2000.0, initial_stop_loss=1990.0
    )
    mt5 = _GlitchThenPresentMT5Client(
        real_positions=[_open_position(ticket="9022", direction="buy", current_price=2005.0)],
        tick=SymbolTick(bid=2005.0, ask=2005.5, timestamp=datetime.now(UTC)),
    )
    monitor = PositionMonitor(mt5_client=mt5, trade_repository=TradeRepository(session))

    result = await monitor.run_cycle(mt5_symbol="XAUUSD", magic_number=42)

    assert result.closed_trades == []
    stored = await TradeRepository(session).get_by_broker_ticket("9022")
    assert stored is not None
    assert stored.status == "open"
    assert trade.status == "open"


async def test_runs_post_mortem_and_notifies_telegram_for_a_losing_reconciled_trade(
    session: AsyncSession,
) -> None:
    symbol = await _make_symbol(session)
    await _make_open_trade(
        session, symbol, broker_ticket="9022", entry_price=2000.0, initial_stop_loss=1990.0
    )
    mt5 = _FakeMT5Client(
        positions=[], tick=SymbolTick(bid=1985.0, ask=1985.5, timestamp=datetime.now(UTC))
    )
    telegram = _FakeTelegramNotifier()
    post_mortem = PostMortemService(
        trade_repository=TradeRepository(session),
        proposal_repository=ImprovementProposalRepository(session),
    )
    monitor = PositionMonitor(
        mt5_client=mt5,
        trade_repository=TradeRepository(session),
        telegram_notifier=telegram,
        telegram_chat_id="chat-1",
        post_mortem_service=post_mortem,
    )

    await monitor.run_cycle(mt5_symbol="XAUUSD", magic_number=42)

    assert len(telegram.sent_messages) == 1
    chat_id, message = telegram.sent_messages[0]
    assert chat_id == "chat-1"
    assert "🔍 Разбор сделки" in message


async def test_reconciliation_persists_shakky_learning_verdict_for_shakky_magic_number(
    session: AsyncSession,
) -> None:
    symbol = await _make_symbol(session)
    trade = await _make_open_trade(
        session, symbol, broker_ticket="9099", entry_price=2000.0, initial_stop_loss=1990.0
    )
    trade.magic_number = 555
    trade.take_profit = 2010.0
    trade.max_favorable_excursion = 15.0
    await TradeRepository(session).add(trade)
    mt5 = _FakeMT5Client(
        positions=[], tick=SymbolTick(bid=2010.0, ask=2010.5, timestamp=datetime.now(UTC))
    )
    post_mortem = PostMortemService(
        trade_repository=TradeRepository(session),
        proposal_repository=ImprovementProposalRepository(session),
    )
    monitor = PositionMonitor(
        mt5_client=mt5,
        trade_repository=TradeRepository(session),
        post_mortem_service=post_mortem,
        shakky_magic_number=555,
    )

    await monitor.run_cycle(mt5_symbol="XAUUSD", magic_number=555)

    stored = await TradeRepository(session).get_by_broker_ticket("9099")
    assert stored is not None
    assert stored.shakky_learning is not None
    assert stored.shakky_learning["tp_too_small"] is True


async def test_reconciliation_skips_shakky_learning_for_a_non_shakky_magic_number(
    session: AsyncSession,
) -> None:
    symbol = await _make_symbol(session)
    await _make_open_trade(
        session, symbol, broker_ticket="9098", entry_price=2000.0, initial_stop_loss=1990.0
    )
    mt5 = _FakeMT5Client(
        positions=[], tick=SymbolTick(bid=1985.0, ask=1985.5, timestamp=datetime.now(UTC))
    )
    post_mortem = PostMortemService(
        trade_repository=TradeRepository(session),
        proposal_repository=ImprovementProposalRepository(session),
    )
    monitor = PositionMonitor(
        mt5_client=mt5,
        trade_repository=TradeRepository(session),
        post_mortem_service=post_mortem,
        shakky_magic_number=555,
    )

    await monitor.run_cycle(mt5_symbol="XAUUSD", magic_number=42)

    stored = await TradeRepository(session).get_by_broker_ticket("9098")
    assert stored is not None
    assert stored.shakky_learning is None


async def test_runs_post_mortem_and_notifies_telegram_for_a_winning_reconciled_trade(
    session: AsyncSession,
) -> None:
    # Per the "Post Trade Analysis" production requirement: every closed
    # trade -- win or loss -- gets a post-trade analysis and Telegram
    # notification, not just losses.
    symbol = await _make_symbol(session)
    await _make_open_trade(
        session, symbol, broker_ticket="9023", entry_price=2000.0, initial_stop_loss=1990.0
    )
    mt5 = _FakeMT5Client(
        positions=[], tick=SymbolTick(bid=2020.0, ask=2020.5, timestamp=datetime.now(UTC))
    )
    telegram = _FakeTelegramNotifier()
    post_mortem = PostMortemService(
        trade_repository=TradeRepository(session),
        proposal_repository=ImprovementProposalRepository(session),
    )
    monitor = PositionMonitor(
        mt5_client=mt5,
        trade_repository=TradeRepository(session),
        telegram_notifier=telegram,
        telegram_chat_id="chat-1",
        post_mortem_service=post_mortem,
    )

    await monitor.run_cycle(mt5_symbol="XAUUSD", magic_number=42)

    assert len(telegram.sent_messages) == 1
    chat_id, message = telegram.sent_messages[0]
    assert chat_id == "chat-1"
    assert "🔍 Разбор сделки" in message
    assert "Открыли бы снова:" in message


async def test_reconciliation_persists_the_post_mortem_verdict_onto_the_trade(
    session: AsyncSession,
) -> None:
    # Per the "Post Trade Learning" production requirement: the verdict
    # must survive beyond the one-shot Telegram notification, not be
    # computed and discarded every cycle.
    symbol = await _make_symbol(session)
    await _make_open_trade(
        session, symbol, broker_ticket="9024", entry_price=2000.0, initial_stop_loss=1990.0
    )
    mt5 = _FakeMT5Client(
        positions=[], tick=SymbolTick(bid=1985.0, ask=1985.5, timestamp=datetime.now(UTC))
    )
    post_mortem = PostMortemService(
        trade_repository=TradeRepository(session),
        proposal_repository=ImprovementProposalRepository(session),
    )
    monitor = PositionMonitor(
        mt5_client=mt5,
        trade_repository=TradeRepository(session),
        telegram_notifier=_FakeTelegramNotifier(),
        telegram_chat_id="chat-1",
        post_mortem_service=post_mortem,
    )

    await monitor.run_cycle(mt5_symbol="XAUUSD", magic_number=42)

    stored = await TradeRepository(session).get_by_broker_ticket("9024")
    assert stored is not None
    assert stored.post_mortem is not None
    assert "would_repeat" in stored.post_mortem
    assert "department_correctness" in stored.post_mortem


async def test_reconciliation_closes_a_trade_even_without_a_post_mortem_service(
    session: AsyncSession,
) -> None:
    symbol = await _make_symbol(session)
    trade = await _make_open_trade(
        session, symbol, broker_ticket="9024", entry_price=2000.0, initial_stop_loss=1990.0
    )
    mt5 = _FakeMT5Client(
        positions=[], tick=SymbolTick(bid=1985.0, ask=1985.5, timestamp=datetime.now(UTC))
    )
    monitor = PositionMonitor(mt5_client=mt5, trade_repository=TradeRepository(session))

    result = await monitor.run_cycle(mt5_symbol="XAUUSD", magic_number=42)

    assert result.closed_trades == [str(trade.id)]


async def test_skips_reconciliation_for_a_trade_with_no_recorded_entry_price(
    session: AsyncSession,
) -> None:
    symbol = await _make_symbol(session)
    trade = await TradeRepository(session).add(
        Trade(
            symbol_id=symbol.id,
            direction="buy",
            status="open",
            volume=1.0,
            entry_price=None,
            stop_loss=1990.0,
            magic_number=42,
            broker_ticket="9026",
        )
    )
    mt5 = _FakeMT5Client(
        positions=[], tick=SymbolTick(bid=1985.0, ask=1985.5, timestamp=datetime.now(UTC))
    )
    monitor = PositionMonitor(mt5_client=mt5, trade_repository=TradeRepository(session))

    result = await monitor.run_cycle(mt5_symbol="XAUUSD", magic_number=42)

    assert result.closed_trades == []
    stored = await TradeRepository(session).get_by_broker_ticket("9026")
    assert stored is not None
    assert stored.id == trade.id
    assert stored.status == "open"


async def test_post_mortem_runs_without_raising_when_telegram_not_configured(
    session: AsyncSession,
) -> None:
    symbol = await _make_symbol(session)
    trade = await _make_open_trade(
        session, symbol, broker_ticket="9025", entry_price=2000.0, initial_stop_loss=1990.0
    )
    mt5 = _FakeMT5Client(
        positions=[], tick=SymbolTick(bid=1985.0, ask=1985.5, timestamp=datetime.now(UTC))
    )
    post_mortem = PostMortemService(
        trade_repository=TradeRepository(session),
        proposal_repository=ImprovementProposalRepository(session),
    )
    monitor = PositionMonitor(
        mt5_client=mt5,
        trade_repository=TradeRepository(session),
        post_mortem_service=post_mortem,
    )

    result = await monitor.run_cycle(mt5_symbol="XAUUSD", magic_number=42)

    assert result.closed_trades == [str(trade.id)]


async def test_dynamic_trigger_moves_stop_to_breakeven_earlier_than_the_fixed_default(
    session: AsyncSession,
) -> None:
    symbol = await _make_symbol(session)
    await _make_open_trade(
        session, symbol, broker_ticket="9500", entry_price=2000.0, initial_stop_loss=1990.0
    )
    # A 0.8R move (8.0) would not trigger the fixed 1.0R default, but does
    # trigger the dynamic 0.7R trigger once order flow strongly opposes
    # the buy position (tightens the trigger below 1.0R).
    mt5 = _FakeMT5Client(
        positions=[_open_position(ticket="9500", direction="buy", current_price=2008.0)]
    )
    monitor = PositionMonitor(mt5_client=mt5, trade_repository=TradeRepository(session))
    dynamic_stop_inputs = DynamicStopInputs(order_flow_bias="bearish", order_flow_confidence=0.9)

    result = await monitor.run_cycle(
        mt5_symbol="XAUUSD", magic_number=42, dynamic_stop_inputs=dynamic_stop_inputs
    )

    assert result.moved_to_breakeven == ["9500"]


async def test_trails_stop_further_once_breakeven_already_reached(
    session: AsyncSession,
) -> None:
    symbol = await _make_symbol(session)
    trade = Trade(
        symbol_id=symbol.id,
        direction="buy",
        status="open",
        volume=1.0,
        entry_price=2000.0,
        stop_loss=2000.0,
        initial_stop_loss=1990.0,
        breakeven_moved=True,
        magic_number=42,
        broker_ticket="9501",
    )
    await TradeRepository(session).add(trade)
    mt5 = _FakeMT5Client(
        positions=[_open_position(ticket="9501", direction="buy", current_price=2020.0)]
    )
    monitor = PositionMonitor(mt5_client=mt5, trade_repository=TradeRepository(session))

    result = await monitor.run_cycle(
        mt5_symbol="XAUUSD", magic_number=42, dynamic_stop_inputs=DynamicStopInputs()
    )

    assert result.trailed == ["9501"]
    stored = await TradeRepository(session).get_by_broker_ticket("9501")
    assert stored is not None
    assert stored.stop_loss > 2000.0
    assert stored.stop_loss < 2020.0


async def test_does_not_trail_the_stop_backward(session: AsyncSession) -> None:
    symbol = await _make_symbol(session)
    # Stop already sits very close to price -- the computed trailing
    # candidate would be less favorable than this, so it must not move.
    trade = Trade(
        symbol_id=symbol.id,
        direction="buy",
        status="open",
        volume=1.0,
        entry_price=2000.0,
        stop_loss=2019.0,
        initial_stop_loss=1990.0,
        breakeven_moved=True,
        magic_number=42,
        broker_ticket="9502",
    )
    await TradeRepository(session).add(trade)
    mt5 = _FakeMT5Client(
        positions=[_open_position(ticket="9502", direction="buy", current_price=2020.0)]
    )
    monitor = PositionMonitor(mt5_client=mt5, trade_repository=TradeRepository(session))

    result = await monitor.run_cycle(
        mt5_symbol="XAUUSD", magic_number=42, dynamic_stop_inputs=DynamicStopInputs()
    )

    assert result.trailed == []
    assert mt5.modify_calls == []


async def test_no_trailing_without_dynamic_stop_inputs(session: AsyncSession) -> None:
    symbol = await _make_symbol(session)
    trade = Trade(
        symbol_id=symbol.id,
        direction="buy",
        status="open",
        volume=1.0,
        entry_price=2000.0,
        stop_loss=2000.0,
        initial_stop_loss=1990.0,
        breakeven_moved=True,
        magic_number=42,
        broker_ticket="9503",
    )
    await TradeRepository(session).add(trade)
    mt5 = _FakeMT5Client(
        positions=[_open_position(ticket="9503", direction="buy", current_price=2020.0)]
    )
    monitor = PositionMonitor(mt5_client=mt5, trade_repository=TradeRepository(session))

    result = await monitor.run_cycle(mt5_symbol="XAUUSD", magic_number=42)

    assert result.trailed == []
    assert mt5.modify_calls == []


async def test_sends_sl_moved_notification_when_trailed(session: AsyncSession) -> None:
    symbol = await _make_symbol(session)
    trade = Trade(
        symbol_id=symbol.id,
        direction="buy",
        status="open",
        volume=1.0,
        entry_price=2000.0,
        stop_loss=2000.0,
        initial_stop_loss=1990.0,
        breakeven_moved=True,
        magic_number=42,
        broker_ticket="9504",
    )
    await TradeRepository(session).add(trade)
    mt5 = _FakeMT5Client(
        positions=[_open_position(ticket="9504", direction="buy", current_price=2020.0)]
    )
    telegram = _FakeTelegramNotifier()
    monitor = PositionMonitor(
        mt5_client=mt5,
        trade_repository=TradeRepository(session),
        telegram_notifier=telegram,
        telegram_chat_id="chat-1",
    )

    await monitor.run_cycle(
        mt5_symbol="XAUUSD", magic_number=42, dynamic_stop_inputs=DynamicStopInputs()
    )

    assert len(telegram.sent_messages) == 1
    chat_id, message = telegram.sent_messages[0]
    assert chat_id == "chat-1"
    assert "🔧 Стоп подвинут" in message


async def test_trailing_does_not_report_success_when_modify_order_fails(
    session: AsyncSession,
) -> None:
    symbol = await _make_symbol(session)
    trade = Trade(
        symbol_id=symbol.id,
        direction="buy",
        status="open",
        volume=1.0,
        entry_price=2000.0,
        stop_loss=2000.0,
        initial_stop_loss=1990.0,
        breakeven_moved=True,
        magic_number=42,
        broker_ticket="9505",
    )
    await TradeRepository(session).add(trade)
    mt5 = _FakeMT5Client(
        positions=[_open_position(ticket="9505", direction="buy", current_price=2020.0)],
        modify_result=OrderResult(
            success=False, broker_ticket=None, filled_price=None, error_message="requote"
        ),
    )
    monitor = PositionMonitor(mt5_client=mt5, trade_repository=TradeRepository(session))

    result = await monitor.run_cycle(
        mt5_symbol="XAUUSD", magic_number=42, dynamic_stop_inputs=DynamicStopInputs()
    )

    assert result.trailed == []
    stored = await TradeRepository(session).get_by_broker_ticket("9505")
    assert stored is not None
    assert stored.stop_loss == 2000.0
