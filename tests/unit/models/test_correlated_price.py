"""Unit tests for the `CorrelatedPrice` ORM model."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from src.models.correlated_price import CorrelatedPrice

pytestmark = pytest.mark.unit


def test_repr_includes_timeframe_and_timestamp() -> None:
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    price = CorrelatedPrice(
        instrument_id=uuid.uuid4(),
        timeframe="H1",
        timestamp=timestamp,
        open=1.10,
        high=1.11,
        low=1.09,
        close=1.105,
        source="mt5",
    )

    assert repr(price) == f"CorrelatedPrice(timeframe='H1', timestamp={timestamp!r})"
