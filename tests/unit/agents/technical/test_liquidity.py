"""Unit tests for `LiquidityAgent`."""

from __future__ import annotations

import pytest

from src.agents.technical.liquidity import LiquidityAgent, find_liquidity_pools
from tests.unit.agents.technical._helpers import make_candle

pytestmark = pytest.mark.unit


def _candles_with_equal_highs_and_sweep() -> list:
    # A flat baseline with two separated spikes to ~109/110 (within
    # tolerance of each other -> one buy-side liquidity pool), each with
    # >=2 candles of padding on both sides so fractal detection (lookaround=2)
    # can confirm them. A final candle then wicks above both but closes below.
    highs_lows = [
        (95, 90),
        (95, 90),
        (95, 90),  # padding
        (109.0, 104),  # spike 1
        (95, 90),
        (95, 90),
        (95, 90),
        (95, 90),  # padding
        (110.0, 105),  # spike 2
        (95, 90),
        (95, 90),
        (95, 90),  # padding
    ]
    candles = [
        make_candle(index, open_=(high + low) / 2, high=high, low=low, close=(high + low) / 2)
        for index, (high, low) in enumerate(highs_lows)
    ]
    # Sweep candle: wicks to 112 (above both ~109/110 highs) but closes at 100.
    candles.append(make_candle(len(highs_lows), open_=105, high=112, low=99, close=100))
    return candles


def test_analyze_reports_unknown_with_no_swings() -> None:
    candles = [make_candle(index, open_=100, high=101, low=99, close=100) for index in range(3)]

    report = LiquidityAgent().analyze(candles)

    assert report.bias == "neutral"
    assert report.confidence == 0.0
    assert report.unknowns


def test_analyze_detects_buy_side_liquidity_pool() -> None:
    report = LiquidityAgent(pool_tolerance_pct=2.0).analyze(_candles_with_equal_highs_and_sweep())

    assert report.metrics["buy_side_pool_count"] >= 1


def test_analyze_detects_sweep_and_reports_bearish_bias() -> None:
    report = LiquidityAgent(pool_tolerance_pct=2.0).analyze(_candles_with_equal_highs_and_sweep())

    assert report.bias == "bearish"
    assert report.confidence > 0.0
    assert any("swept" in note for note in report.supporting_evidence)


def test_analyze_no_sweep_reports_neutral() -> None:
    highs_lows = [(95, 90), (98, 93), (96, 91), (97, 92), (95, 90)]
    candles = [
        make_candle(index, open_=(high + low) / 2, high=high, low=low, close=(high + low) / 2)
        for index, (high, low) in enumerate(highs_lows)
    ]

    report = LiquidityAgent().analyze(candles)

    assert report.bias == "neutral"
    assert report.confidence == 0.0


def _candles_with_equal_lows_and_sweep() -> list:
    # Mirror image of `_candles_with_equal_highs_and_sweep` (price -> 200 -
    # price): padding ties high at 110 (irrelevant here — the final sweep
    # candle's high stays at 101, well below it, so no accidental buy-side
    # sweep), while the two dips at ~90/91 form a genuine sell-side pool.
    highs_lows = [
        (110, 105),
        (110, 105),
        (110, 105),  # padding
        (96.0, 91.0),  # dip 1 (low)
        (110, 105),
        (110, 105),
        (110, 105),
        (110, 105),  # padding
        (95.0, 90.0),  # dip 2 (low, within tolerance of 91)
        (110, 105),
        (110, 105),
        (110, 105),  # padding
    ]
    candles = [
        make_candle(index, open_=(high + low) / 2, high=high, low=low, close=(high + low) / 2)
        for index, (high, low) in enumerate(highs_lows)
    ]
    # Sweep candle: wicks to 85 (below both ~90/91 lows) but closes at 95.
    candles.append(make_candle(len(highs_lows), open_=90, high=101, low=85, close=95))
    return candles


def test_analyze_detects_sell_side_sweep_and_reports_bullish_bias() -> None:
    report = LiquidityAgent(pool_tolerance_pct=2.0).analyze(_candles_with_equal_lows_and_sweep())

    assert report.bias == "bullish"
    assert report.confidence > 0.0
    assert any("Sell-side" in note for note in report.supporting_evidence)


def test_analyze_detects_both_sides_swept_reports_neutral_with_conflict_note() -> None:
    highs_lows = [
        (95, 90),
        (95, 90),
        (95, 90),
        (109.0, 104),
        (95, 90),
        (95, 90),
        (95, 90),
        (95, 90),
        (110.0, 105),
        (95, 90),
        (95, 90),
        (95, 90),
        (95, 90),
        (95, 90),
        (95, 90),
        (95, 90),
        (95, 90.0),
        (95, 90),
        (95, 90),
        (95, 90),
        (95, 90),
        (95, 91.0),
        (95, 90),
        (95, 90),
        (95, 90),
    ]
    candles = [
        make_candle(index, open_=(high + low) / 2, high=high, low=low, close=(high + low) / 2)
        for index, (high, low) in enumerate(highs_lows)
    ]
    # Wicks above the ~110 buy-side pool AND below the ~90 sell-side pool,
    # closing back in between both.
    candles.append(make_candle(len(highs_lows), open_=100, high=112, low=85, close=100))

    report = LiquidityAgent(pool_tolerance_pct=2.0).analyze(candles)

    assert report.bias == "neutral"
    assert any("conflicting" in note for note in report.opposing_evidence)


def test_find_pools_returns_empty_for_no_prices() -> None:
    assert find_liquidity_pools([], tolerance_pct=1.0, kind="buy_side") == []


def test_find_pools_separates_distant_prices_into_multiple_pools() -> None:
    pools = find_liquidity_pools([100.0, 100.0, 200.0, 200.0], tolerance_pct=1.0, kind="buy_side")

    assert len(pools) == 2
