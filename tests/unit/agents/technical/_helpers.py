"""Shared candle-building helpers for Technical Department agent tests."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from src.models.candle import Candle

SYMBOL_ID = uuid.uuid4()
BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


def make_candle(
    index: int,
    *,
    open_: float,
    high: float,
    low: float,
    close: float,
    volume: float | None = None,
) -> Candle:
    """Build a single `Candle` at a fixed hourly cadence starting at `BASE_TIME`."""
    return Candle(
        symbol_id=SYMBOL_ID,
        timeframe="H1",
        timestamp=BASE_TIME + timedelta(hours=index),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        source="test_fixture",
    )


def make_series(closes: list[float], *, spread: float = 1.0) -> list[Candle]:
    """Build a simple candle series from a list of closing prices.

    Each candle's open equals the previous close (or the first close for
    the first candle), with high/low offset by a fixed `spread`.
    """
    candles: list[Candle] = []
    previous_close = closes[0]
    for index, close in enumerate(closes):
        open_ = previous_close
        high = max(open_, close) + spread
        low = min(open_, close) - spread
        candles.append(make_candle(index, open_=open_, high=high, low=low, close=close))
        previous_close = close
    return candles
