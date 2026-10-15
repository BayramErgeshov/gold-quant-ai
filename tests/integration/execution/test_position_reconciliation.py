"""Integration tests for `reconcile_positions`."""

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
from src.core.execution.position_reconciliation import reconcile_positions
from src.models.symbol import Symbol
from src.models.trade import Trade
from src.repositories.symbol_repository import SymbolRepository
from src.repositories.trade_repository import TradeRepository

pytestmark = pytest.mark.asyncio


class _FakeMT5Client(MT5Client):
    def __init__(self, *, positions: list[OpenPosition]) -> None:
        self._positions = positions

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
        return self._positions


def _position(ticket: str) -> OpenPosition:
    return OpenPosition(
        ticket=ticket,
        symbol="XAUUSD",
        direction="buy",
        volume=1.0,
        entry_price=2000.0,
        stop_loss=1990.0,
        take_profit=2020.0,
        current_price=2005.0,
        profit=5.0,
        magic_number=42,
        opened_at=datetime.now(UTC),
    )


async def _make_open_trade(session: AsyncSession, symbol: Symbol, *, broker_ticket: str) -> Trade:
    trade = Trade(
        symbol_id=symbol.id,
        direction="buy",
        status="open",
        volume=1.0,
        entry_price=2000.0,
        stop_loss=1990.0,
        initial_stop_loss=1990.0,
        magic_number=42,
        broker_ticket=broker_ticket,
    )
    return await TradeRepository(session).add(trade)


async def test_reconcile_positions_reports_clean_when_everything_matches(
    session: AsyncSession,
) -> None:
    symbol = await SymbolRepository(session).add(Symbol(name="XAUUSD", display_name="Gold"))
    await _make_open_trade(session, symbol, broker_ticket="9001")
    mt5 = _FakeMT5Client(positions=[_position("9001")])

    report = await reconcile_positions(
        mt5_client=mt5, trade_repository=TradeRepository(session), mt5_symbol="XAUUSD"
    )

    assert report.is_clean is True
    assert report.matched_count == 1
    assert report.broker_tickets_missing_from_journal == []
    assert report.journal_trades_missing_from_broker == []


async def test_reconcile_positions_flags_a_broker_position_with_no_journal_row(
    session: AsyncSession,
) -> None:
    mt5 = _FakeMT5Client(positions=[_position("9002")])

    report = await reconcile_positions(
        mt5_client=mt5, trade_repository=TradeRepository(session), mt5_symbol="XAUUSD"
    )

    assert report.is_clean is False
    assert report.broker_tickets_missing_from_journal == ["9002"]
    assert report.journal_trades_missing_from_broker == []


async def test_reconcile_positions_flags_a_journal_row_with_no_broker_position(
    session: AsyncSession,
) -> None:
    symbol = await SymbolRepository(session).add(Symbol(name="XAUUSD", display_name="Gold"))
    await _make_open_trade(session, symbol, broker_ticket="9003")
    mt5 = _FakeMT5Client(positions=[])

    report = await reconcile_positions(
        mt5_client=mt5, trade_repository=TradeRepository(session), mt5_symbol="XAUUSD"
    )

    assert report.is_clean is False
    assert report.broker_tickets_missing_from_journal == []
    assert report.journal_trades_missing_from_broker == ["9003"]
