"""Unit tests for real-DOM order flow analysis."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.core.execution.mt5_client import OrderBookLevel, OrderBookSnapshot
from src.engines.order_flow_engine.real_order_flow import analyze_real_order_flow

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _snapshot(levels: list[OrderBookLevel]) -> OrderBookSnapshot:
    return OrderBookSnapshot(symbol="XAUUSD", timestamp=_NOW, levels=levels)


def test_imbalance_favors_the_larger_side() -> None:
    snapshot = _snapshot(
        [
            OrderBookLevel(price=2001.0, volume=100.0, side="bid"),
            OrderBookLevel(price=2001.5, volume=10.0, side="ask"),
        ]
    )

    report = analyze_real_order_flow(snapshot)

    assert report.imbalance > 0
    assert report.bullish_probability > report.bearish_probability
    assert any("bid" in note for note in report.supporting_evidence)


def test_imbalance_is_zero_with_no_volume() -> None:
    report = analyze_real_order_flow(_snapshot([]))

    assert report.imbalance == 0.0
    assert report.confidence == 0.0


def test_detects_a_liquidity_wall() -> None:
    snapshot = _snapshot(
        [
            OrderBookLevel(price=2001.0, volume=500.0, side="bid"),  # wall
            OrderBookLevel(price=2000.9, volume=10.0, side="bid"),
            OrderBookLevel(price=2000.8, volume=12.0, side="bid"),
            OrderBookLevel(price=2001.5, volume=10.0, side="ask"),
        ]
    )

    report = analyze_real_order_flow(snapshot)

    assert len(report.liquidity_walls) == 1
    assert report.liquidity_walls[0].level.side == "bid"
    assert report.liquidity_walls[0].volume_ratio >= 3.0


def test_high_liquidity_zones_are_the_largest_levels() -> None:
    snapshot = _snapshot(
        [
            OrderBookLevel(price=2001.0, volume=5.0, side="bid"),
            OrderBookLevel(price=2000.9, volume=50.0, side="bid"),
            OrderBookLevel(price=2001.5, volume=20.0, side="ask"),
        ]
    )

    report = analyze_real_order_flow(snapshot)

    assert report.high_liquidity_zones[0].volume == 50.0


def test_detects_a_swept_wall_between_snapshots() -> None:
    previous = _snapshot(
        [
            OrderBookLevel(price=2000.0, volume=500.0, side="bid"),
            OrderBookLevel(price=1999.9, volume=10.0, side="bid"),
            OrderBookLevel(price=1999.8, volume=12.0, side="bid"),
        ]
    )
    # The 2000.0 bid wall is gone in the new snapshot -> candidate sweep,
    # which (a removed bid-side wall/support) is a bearish signal.
    current = _snapshot(
        [
            OrderBookLevel(price=1998.0, volume=10.0, side="bid"),
            OrderBookLevel(price=1997.9, volume=12.0, side="bid"),
        ]
    )

    report = analyze_real_order_flow(current, previous_snapshot=previous)

    assert len(report.swept_walls) == 1
    assert report.swept_walls[0].level.price == 2000.0
    assert any("sweep" in note for note in report.supporting_evidence)


def test_no_swept_walls_without_a_previous_snapshot() -> None:
    snapshot = _snapshot([OrderBookLevel(price=2000.0, volume=500.0, side="bid")])

    report = analyze_real_order_flow(snapshot)

    assert report.swept_walls == []
