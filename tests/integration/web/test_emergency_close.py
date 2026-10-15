"""Integration tests for the "EMERGENCY CLOSE" web UI action."""

from __future__ import annotations

import uuid

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
from src.interfaces.web.emergency_close import emergency_close_all_positions
from src.interfaces.web.settings_service import get_current_settings
from src.models.trade import Trade
from src.repositories.trade_repository import TradeRepository

pytestmark = pytest.mark.asyncio

_SYMBOL_ID = uuid.uuid4()


class _FakeEmergencyMT5Client(MT5Client):
    """Closes every requested ticket at a fixed price, except any in `reject_tickets`."""

    def __init__(
        self,
        *,
        connected: bool = True,
        fill_price: float = 2010.0,
        reject_tickets: set[str] | None = None,
    ) -> None:
        self._connected = connected
        self._fill_price = fill_price
        self._reject_tickets = reject_tickets or set()
        self.close_requests: list[str] = []

    async def connect(self) -> bool:
        return self._connected

    async def is_connected(self) -> bool:
        return self._connected

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
        self.close_requests.append(broker_ticket)
        if broker_ticket in self._reject_tickets:
            return OrderResult(
                success=False,
                broker_ticket=broker_ticket,
                filled_price=None,
                error_message="rejected",
            )
        return OrderResult(success=True, broker_ticket=broker_ticket, filled_price=self._fill_price)

    async def cancel_order(self, broker_ticket: str) -> OrderResult:
        raise NotImplementedError

    async def get_candles(self, symbol: str, timeframe: str, count: int) -> list[dict[str, object]]:
        raise NotImplementedError

    async def get_symbol_tick(self, symbol: str) -> SymbolTick:
        raise NotImplementedError

    async def get_open_positions(
        self, *, symbol: str | None = None, magic_number: int | None = None
    ) -> list[OpenPosition]:
        raise NotImplementedError

    async def get_order_book(self, symbol: str) -> OrderBookSnapshot | None:
        raise NotImplementedError


async def _open_trade(
    session: AsyncSession, *, broker_ticket: str, direction: str = "buy"
) -> Trade:
    return await TradeRepository(session).add(
        Trade(
            symbol_id=_SYMBOL_ID,
            direction=direction,
            status="open",
            volume=1.0,
            entry_price=2000.0,
            stop_loss=1990.0,
            magic_number=1,
            broker_ticket=broker_ticket,
        )
    )


async def test_closes_every_open_position_and_disables_auto_trading(session: AsyncSession) -> None:
    await _open_trade(session, broker_ticket="9001")
    await _open_trade(session, broker_ticket="9002", direction="sell")

    mt5 = _FakeEmergencyMT5Client(fill_price=2010.0)
    result = await emergency_close_all_positions(session, mt5)

    assert result.mt5_connected is True
    assert sorted(result.closed_tickets) == ["9001", "9002"]
    assert result.failed_tickets == []
    assert sorted(mt5.close_requests) == ["9001", "9002"]

    trades = await TradeRepository(session).list_by_status("closed", limit=10)
    assert len(trades) == 2
    assert all(trade.exit_price == 2010.0 for trade in trades)
    assert all(trade.realized_pnl is not None for trade in trades)

    settings = await get_current_settings(session)
    assert settings.auto_trading_enabled is False


async def test_reports_failed_closes_without_marking_the_trade_closed(
    session: AsyncSession,
) -> None:
    await _open_trade(session, broker_ticket="9003")

    mt5 = _FakeEmergencyMT5Client(reject_tickets={"9003"})
    result = await emergency_close_all_positions(session, mt5)

    assert result.closed_tickets == []
    assert result.failed_tickets == ["9003"]

    trades = await TradeRepository(session).list_by_status("open", limit=10)
    assert len(trades) == 1
    assert trades[0].broker_ticket == "9003"


async def test_returns_early_when_mt5_connect_fails(session: AsyncSession) -> None:
    await _open_trade(session, broker_ticket="9004")

    mt5 = _FakeEmergencyMT5Client(connected=False)
    result = await emergency_close_all_positions(session, mt5)

    assert result.mt5_connected is False
    assert result.closed_tickets == []
    assert mt5.close_requests == []

    # Auto-trading is still disabled even when MT5 is unreachable -- the
    # safest default when the operator has hit EMERGENCY CLOSE.
    settings = await get_current_settings(session)
    assert settings.auto_trading_enabled is False


async def test_ignores_open_trades_with_no_broker_ticket(session: AsyncSession) -> None:
    await TradeRepository(session).add(
        Trade(
            symbol_id=_SYMBOL_ID,
            direction="buy",
            status="open",
            volume=1.0,
            entry_price=2000.0,
            stop_loss=1990.0,
            magic_number=1,
            broker_ticket=None,
        )
    )

    mt5 = _FakeEmergencyMT5Client()
    result = await emergency_close_all_positions(session, mt5)

    assert result.closed_tickets == []
    assert mt5.close_requests == []
