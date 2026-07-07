"""Unit tests for the `Candle` ORM model."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from src.models.candle import Candle

pytestmark = pytest.mark.unit


def test_repr_includes_timeframe_and_timestamp() -> None:
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    candle = Candle(
        symbol_id=uuid.uuid4(),
        timeframe="H1",
        timestamp=timestamp,
        open=3400.0,
        high=3410.0,
        low=3395.0,
        close=3405.0,
        source="twelvedata",
    )

    assert repr(candle) == f"Candle(timeframe='H1', timestamp={timestamp!r})"
