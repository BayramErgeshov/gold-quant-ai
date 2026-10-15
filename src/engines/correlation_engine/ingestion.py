"""Live candle ingestion for correlated (non-tradable) reference instruments.

Mirrors `src.engines.historical_engine.mt5_ingestion.MT5HistoricalIngestionService`'s
shape, but targets `CorrelatedPrice`/`CorrelatedInstrument` rather than the
trading-critical `Candle`/`Symbol` tables (see those models' docstrings
for why they are kept separate). Validation here is intentionally lighter
than `src.engines.historical_engine.validation` — correlated instruments
only ever adjust confidence, never gate order placement, so a basic OHLC
integrity check is proportionate rather than the full trading-data
quality pipeline.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from src.common.logging import get_logger
from src.core.execution.mt5_client import MT5Client
from src.models.correlated_price import CorrelatedPrice
from src.repositories.correlated_price_repository import CorrelatedPriceRepository

logger = get_logger(__name__)

_SOURCE_NAME = "mt5"


@dataclass(frozen=True, slots=True)
class CorrelatedIngestionResult:
    """Outcome of a single correlated-instrument ingestion run.

    Attributes:
        requested: Number of bars returned by MT5.
        valid: Number that passed basic OHLC integrity checks.
        inserted: Number newly inserted (excludes already-stored prices).
        skipped_reasons: Human-readable reasons for any bar rejected.
    """

    requested: int
    valid: int
    inserted: int
    skipped_reasons: list[str] = field(default_factory=list)


def _to_price(instrument_id: uuid.UUID, timeframe: str, raw: dict[str, Any]) -> CorrelatedPrice:
    return CorrelatedPrice(
        instrument_id=instrument_id,
        timeframe=timeframe,
        timestamp=datetime.fromtimestamp(raw["time"], tz=UTC),
        open=float(raw["open"]),
        high=float(raw["high"]),
        low=float(raw["low"]),
        close=float(raw["close"]),
        volume=float(raw["tick_volume"]),
        source=_SOURCE_NAME,
    )


def _is_valid(price: CorrelatedPrice) -> bool:
    return (
        price.high >= price.low
        and price.high >= max(price.open, price.close)
        and price.low <= min(price.open, price.close)
    )


class CorrelatedInstrumentIngestionService:
    """Downloads, validates and stores OHLCV bars for a correlated instrument."""

    def __init__(
        self, *, price_repository: CorrelatedPriceRepository, mt5_client: MT5Client
    ) -> None:
        """Initialize the service (constructor injection).

        Args:
            price_repository: Persists validated prices.
            mt5_client: Live MT5 gateway to fetch bars from.
        """
        self._prices = price_repository
        self._mt5 = mt5_client

    async def ingest(
        self, instrument_id: uuid.UUID, *, mt5_symbol: str, timeframe: str, count: int = 500
    ) -> CorrelatedIngestionResult:
        """Download, validate and store bars for one correlated instrument/timeframe.

        Args:
            instrument_id: The `CorrelatedInstrument` id these bars belong to.
            mt5_symbol: The symbol name as known to the MT5 terminal.
            timeframe: One of `src.models.candle.TIMEFRAMES`.
            count: Number of most recent bars to request.

        Returns:
            A `CorrelatedIngestionResult`. `requested == 0` if MT5 returned
            no data for this symbol/timeframe — never a fabricated result.
        """
        raw_prices = await self._mt5.get_candles(mt5_symbol, timeframe, count)
        prices = [_to_price(instrument_id, timeframe, raw) for raw in raw_prices]

        valid_prices: list[CorrelatedPrice] = []
        skipped_reasons: list[str] = []
        for price in prices:
            if _is_valid(price):
                valid_prices.append(price)
            else:
                skipped_reasons.append(f"invalid_ohlc:{price.timestamp.isoformat()}")

        inserted = await self._prices.insert_new(valid_prices)
        logger.info(
            "correlated_instrument_ingestion_completed",
            instrument_id=str(instrument_id),
            mt5_symbol=mt5_symbol,
            timeframe=timeframe,
            requested=len(prices),
            valid=len(valid_prices),
            inserted=inserted,
        )
        return CorrelatedIngestionResult(
            requested=len(prices),
            valid=len(valid_prices),
            inserted=inserted,
            skipped_reasons=skipped_reasons,
        )
