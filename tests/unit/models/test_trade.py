"""Unit tests for the `Trade` ORM model."""

from __future__ import annotations

import uuid

import pytest

from src.models.trade import Trade

pytestmark = pytest.mark.unit


def test_repr_includes_direction_and_status() -> None:
    trade = Trade(
        symbol_id=uuid.uuid4(),
        direction="buy",
        status="pending",
        volume=1.0,
        stop_loss=1990.0,
        magic_number=12345,
    )

    assert repr(trade) == "Trade(direction='buy', status='pending')"
