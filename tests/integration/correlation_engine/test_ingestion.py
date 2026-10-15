"""Integration tests for `CorrelatedInstrumentIngestionService`."""

from __future__ import annotations

from datetime import UTC, datetime

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
from src.engines.correlation_engine.ingestion import CorrelatedInstrumentIngestionService
from src.models.correlated_instrument import CorrelatedInstrument
from src.repositories.correlated_instrument_repository import CorrelatedInstrumentRepository
from src.repositories.correlated_price_repository import CorrelatedPriceRepository

_BASE_TIME = int(datetime(2026, 1, 1, tzinfo=UTC).timestamp())
_SECONDS_PER_DAY = 86400

_SAMPLE_PRICES: list[dict[str, object]] = [
    {
        "time": _BASE_TIME,
        "open": 1.10,
        "high": 1.11,
        "low": 1.09,
        "close": 1.105,
        "tick_volume": 800.0,
    },
    {
        "time": _BASE_TIME + _SECONDS_PER_DAY,
        "open": 1.105,
        "high": 1.115,
        "low": 1.10,
        "close": 1.112,
        "tick_volume": 900.0,
    },
]


class _FakeMT5Client(MT5Client):
    def __init__(self, *, prices: list[dict[str, object]] | None = None) -> None:
        self.prices = prices if prices is not None else _SAMPLE_PRICES
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
        return self.prices

    async def get_symbol_tick(self, symbol: str) -> SymbolTick:
        raise NotImplementedError

    async def get_order_book(self, symbol: str) -> OrderBookSnapshot | None:
        return None

    async def get_open_positions(
        self, *, symbol: str | None = None, magic_number: int | None = None
    ) -> list[OpenPosition]:
        raise NotImplementedError


async def _make_instrument(session: AsyncSession) -> CorrelatedInstrument:
    return await CorrelatedInstrumentRepository(session).add(
        CorrelatedInstrument(
            name="EURUSD", display_name="Euro vs US Dollar", mt5_symbol="EURUSD", category="fx"
        )
    )


async def test_ingest_stores_validated_prices(session: AsyncSession) -> None:
    instrument = await _make_instrument(session)
    mt5_client = _FakeMT5Client()
    service = CorrelatedInstrumentIngestionService(
        price_repository=CorrelatedPriceRepository(session), mt5_client=mt5_client
    )

    result = await service.ingest(instrument.id, mt5_symbol="EURUSD", timeframe="D1", count=500)

    assert result.requested == 2
    assert result.valid == 2
    assert result.inserted == 2
    assert result.skipped_reasons == []
    assert mt5_client.last_request == ("EURUSD", "D1", 500)

    stored = await CorrelatedPriceRepository(session).list_most_recent(
        instrument.id, "D1", count=10
    )
    assert len(stored) == 2
    assert stored[0].source == "mt5"


async def test_ingest_is_idempotent(session: AsyncSession) -> None:
    instrument = await _make_instrument(session)
    mt5_client = _FakeMT5Client()
    service = CorrelatedInstrumentIngestionService(
        price_repository=CorrelatedPriceRepository(session), mt5_client=mt5_client
    )

    await service.ingest(instrument.id, mt5_symbol="EURUSD", timeframe="D1")
    second_result = await service.ingest(instrument.id, mt5_symbol="EURUSD", timeframe="D1")

    assert second_result.inserted == 0


async def test_ingest_handles_empty_response(session: AsyncSession) -> None:
    instrument = await _make_instrument(session)
    mt5_client = _FakeMT5Client(prices=[])
    service = CorrelatedInstrumentIngestionService(
        price_repository=CorrelatedPriceRepository(session), mt5_client=mt5_client
    )

    result = await service.ingest(instrument.id, mt5_symbol="EURUSD", timeframe="D1")

    assert result.requested == 0
    assert result.inserted == 0


async def test_ingest_skips_invalid_ohlc(session: AsyncSession) -> None:
    instrument = await _make_instrument(session)
    bad_prices: list[dict[str, object]] = [
        {
            "time": _BASE_TIME,
            "open": 1.10,
            "high": 1.09,
            "low": 1.095,
            "close": 1.10,
            "tick_volume": 800.0,
        },
    ]
    mt5_client = _FakeMT5Client(prices=bad_prices)
    service = CorrelatedInstrumentIngestionService(
        price_repository=CorrelatedPriceRepository(session), mt5_client=mt5_client
    )

    result = await service.ingest(instrument.id, mt5_symbol="EURUSD", timeframe="D1")

    assert result.requested == 1
    assert result.valid == 0
    assert result.inserted == 0
    assert len(result.skipped_reasons) == 1
    assert result.skipped_reasons[0].startswith("invalid_ohlc:")
