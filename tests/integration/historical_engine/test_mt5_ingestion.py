"""Integration tests for `MT5HistoricalIngestionService`."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.execution.mt5_client import (
    AccountInfo,
    MT5Client,
    OpenPosition,
    OrderRequest,
    OrderResult,
    SymbolTick,
)
from src.engines.historical_engine.mt5_ingestion import MT5HistoricalIngestionService
from src.models.symbol import Symbol
from src.repositories.candle_repository import CandleRepository
from src.repositories.symbol_repository import SymbolRepository

_BASE_TIME = int(datetime(2026, 1, 1, tzinfo=UTC).timestamp())
_SECONDS_PER_DAY = 86400

_SAMPLE_CANDLES: list[dict[str, object]] = [
    {
        "time": _BASE_TIME,
        "open": 3390.0,
        "high": 3400.0,
        "low": 3380.0,
        "close": 3398.0,
        "tick_volume": 800.0,
        "spread": 13,
        "real_volume": 0.0,
    },
    {
        "time": _BASE_TIME + _SECONDS_PER_DAY,
        "open": 3398.0,
        "high": 3410.0,
        "low": 3390.0,
        "close": 3408.0,
        "tick_volume": 900.0,
        "spread": 13,
        "real_volume": 0.0,
    },
    {
        "time": _BASE_TIME + 2 * _SECONDS_PER_DAY,
        "open": 3408.0,
        "high": 3420.0,
        "low": 3400.0,
        "close": 3415.0,
        "tick_volume": 1000.0,
        "spread": 13,
        "real_volume": 0.0,
    },
]


class _FakeMT5Client(MT5Client):
    def __init__(self, *, candles: list[dict[str, object]] | None = None) -> None:
        self.candles = candles if candles is not None else _SAMPLE_CANDLES
        self.last_request: tuple[str, str, int] | None = None

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
        self.last_request = (symbol, timeframe, count)
        return self.candles

    async def get_symbol_tick(self, symbol: str) -> SymbolTick:
        raise NotImplementedError

    async def get_open_positions(
        self, *, symbol: str | None = None, magic_number: int | None = None
    ) -> list[OpenPosition]:
        raise NotImplementedError


async def _make_symbol(session: AsyncSession) -> Symbol:
    return await SymbolRepository(session).add(Symbol(name="XAUUSD", display_name="Gold"))


async def test_ingest_stores_validated_candles(session: AsyncSession) -> None:
    symbol = await _make_symbol(session)
    mt5_client = _FakeMT5Client()
    service = MT5HistoricalIngestionService(
        candle_repository=CandleRepository(session), mt5_client=mt5_client
    )

    result = await service.ingest(symbol.id, mt5_symbol="XAUUSD", timeframe="D1", count=5000)

    assert result.requested == 3
    assert result.valid == 3
    assert result.inserted == 3
    assert result.issues == []
    assert mt5_client.last_request == ("XAUUSD", "D1", 5000)

    stored = await CandleRepository(session).list_range(symbol.id, "D1")
    assert len(stored) == 3
    assert stored[0].source == "mt5"


async def test_ingest_is_idempotent_on_repeated_calls(session: AsyncSession) -> None:
    symbol = await _make_symbol(session)
    mt5_client = _FakeMT5Client()
    service = MT5HistoricalIngestionService(
        candle_repository=CandleRepository(session), mt5_client=mt5_client
    )

    await service.ingest(symbol.id, mt5_symbol="XAUUSD", timeframe="D1")
    second_result = await service.ingest(symbol.id, mt5_symbol="XAUUSD", timeframe="D1")

    assert second_result.inserted == 0
    stored = await CandleRepository(session).list_range(symbol.id, "D1")
    assert len(stored) == 3


async def test_ingest_handles_empty_response(session: AsyncSession) -> None:
    symbol = await _make_symbol(session)
    mt5_client = _FakeMT5Client(candles=[])
    service = MT5HistoricalIngestionService(
        candle_repository=CandleRepository(session), mt5_client=mt5_client
    )

    result = await service.ingest(symbol.id, mt5_symbol="XAUUSD", timeframe="D1")

    assert result.requested == 0
    assert result.inserted == 0


async def test_ingest_excludes_invalid_candles(session: AsyncSession) -> None:
    symbol = await _make_symbol(session)
    bad_candles: list[dict[str, object]] = [
        {
            "time": _BASE_TIME,
            "open": 3400.0,
            "high": 3390.0,
            "low": 3395.0,
            "close": 3398.0,
            "tick_volume": 800.0,
            "spread": 13,
            "real_volume": 0.0,
        },
    ]
    mt5_client = _FakeMT5Client(candles=bad_candles)
    service = MT5HistoricalIngestionService(
        candle_repository=CandleRepository(session), mt5_client=mt5_client
    )

    result = await service.ingest(symbol.id, mt5_symbol="XAUUSD", timeframe="D1")

    assert result.requested == 1
    assert result.valid == 0
    assert result.inserted == 0
    assert any(issue.kind == "invalid_ohlc" for issue in result.issues)
