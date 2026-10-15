"""Unit tests for `OrderFlowAnalysisService`."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from src.core.execution.mt5_client import (
    AccountInfo,
    MT5Client,
    OpenPosition,
    OrderBookLevel,
    OrderBookSnapshot,
    OrderRequest,
    OrderResult,
    SymbolTick,
)
from src.engines.order_flow_engine.service import OrderFlowAnalysisService
from src.models.candle import Candle

pytestmark = pytest.mark.unit

_BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


class _FakeMT5Client(MT5Client):
    def __init__(self, *, order_books: list[OrderBookSnapshot | None]) -> None:
        self._order_books = order_books
        self.call_count = 0

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
        result = self._order_books[self.call_count]
        self.call_count += 1
        return result

    async def get_open_positions(
        self, *, symbol: str | None = None, magic_number: int | None = None
    ) -> list[OpenPosition]:
        raise NotImplementedError


def _candles() -> list[Candle]:
    return [
        Candle(
            symbol_id=uuid.uuid4(),
            timeframe="M5",
            timestamp=_BASE_TIME + timedelta(minutes=index * 5),
            open=100.0 + index,
            high=101.0 + index,
            low=99.0 + index,
            close=101.0 + index,
            volume=100.0,
            source="test_fixture",
        )
        for index in range(20)
    ]


async def test_analyze_uses_real_dom_when_available() -> None:
    snapshot = OrderBookSnapshot(
        symbol="XAUUSD",
        timestamp=_BASE_TIME,
        levels=[
            OrderBookLevel(price=2001.0, volume=100.0, side="bid"),
            OrderBookLevel(price=2001.5, volume=10.0, side="ask"),
        ],
    )
    mt5 = _FakeMT5Client(order_books=[snapshot])
    service = OrderFlowAnalysisService(mt5_client=mt5)

    result = await service.analyze("XAUUSD", _candles())

    assert result.source == "real_dom"
    assert result.real_report is not None
    assert result.synthetic_report is None


async def test_analyze_falls_back_to_synthetic_when_dom_unavailable() -> None:
    mt5 = _FakeMT5Client(order_books=[None])
    service = OrderFlowAnalysisService(mt5_client=mt5)

    result = await service.analyze("XAUUSD", _candles())

    assert result.source == "synthetic"
    assert result.synthetic_report is not None
    assert result.real_report is None


async def test_analyze_remembers_previous_snapshot_across_calls() -> None:
    first_snapshot = OrderBookSnapshot(
        symbol="XAUUSD",
        timestamp=_BASE_TIME,
        levels=[
            OrderBookLevel(price=2000.0, volume=500.0, side="bid"),
            OrderBookLevel(price=1999.9, volume=10.0, side="bid"),
            OrderBookLevel(price=1999.8, volume=12.0, side="bid"),
        ],
    )
    second_snapshot = OrderBookSnapshot(
        symbol="XAUUSD",
        timestamp=_BASE_TIME + timedelta(minutes=1),
        levels=[OrderBookLevel(price=1998.0, volume=10.0, side="bid")],
    )
    mt5 = _FakeMT5Client(order_books=[first_snapshot, second_snapshot])
    service = OrderFlowAnalysisService(mt5_client=mt5)

    await service.analyze("XAUUSD", _candles())
    second_result = await service.analyze("XAUUSD", _candles())

    assert second_result.real_report is not None
    assert len(second_result.real_report.swept_walls) == 1
