"""Unit tests for the `MarketRegime` ORM model."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from src.models.market_regime import MarketRegime

pytestmark = pytest.mark.unit


def test_repr_includes_regime_and_start() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    regime = MarketRegime(
        symbol_id=uuid.uuid4(),
        timeframe="D1",
        start_timestamp=start,
        end_timestamp=datetime(2026, 2, 1, tzinfo=UTC),
        regime="bull_trend",
    )

    assert repr(regime) == f"MarketRegime(regime='bull_trend', start={start!r})"
