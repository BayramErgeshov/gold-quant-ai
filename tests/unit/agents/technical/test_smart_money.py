"""Unit tests for `SmartMoneyAgent`."""

from __future__ import annotations

import pytest

from src.agents.technical.smart_money import (
    SmartMoneyAgent,
    find_displacement_index,
    find_fair_value_gaps,
)
from tests.unit.agents.technical._helpers import make_candle

pytestmark = pytest.mark.unit


def _calm_then_displacement_candles() -> list:
    candles = []
    close = 100.0
    for index in range(8):
        open_ = close
        close = 101.0 if close == 100.0 else 100.0
        candles.append(
            make_candle(
                index,
                open_=open_,
                high=max(open_, close) + 1,
                low=min(open_, close) - 1,
                close=close,
            )
        )
    # Large bullish displacement candle: body of 39 vs a recent average body of ~1.
    candles.append(make_candle(8, open_=101.0, high=141.0, low=100.0, close=140.0))
    return candles


def test_analyze_reports_unknown_with_too_few_candles() -> None:
    candles = [make_candle(index, open_=100, high=101, low=99, close=100) for index in range(3)]

    report = SmartMoneyAgent().analyze(candles)

    assert report.bias == "neutral"
    assert report.confidence == 0.0
    assert report.unknowns


def test_find_displacement_index_detects_large_body() -> None:
    candles = _calm_then_displacement_candles()

    index = find_displacement_index(candles)

    assert index == 8


def test_find_displacement_index_none_when_no_displacement() -> None:
    candles = [make_candle(index, open_=100, high=101, low=99, close=100.5) for index in range(10)]

    assert find_displacement_index(candles) is None


def test_analyze_detects_bullish_displacement_and_order_block() -> None:
    report = SmartMoneyAgent().analyze(_calm_then_displacement_candles())

    assert report.bias == "bullish"
    assert report.confidence > 0.0
    assert "order_block_high" in report.metrics
    assert "order_block_low" in report.metrics


def test_find_fair_value_gaps_detects_bullish_gap() -> None:
    candles = [
        make_candle(0, open_=100, high=101, low=99, close=100),
        make_candle(1, open_=100, high=110, low=100, close=109),
        make_candle(2, open_=109, high=115, low=105, close=112),
    ]

    gaps = find_fair_value_gaps(candles)

    assert len(gaps) == 1
    assert gaps[0].direction == "bullish"


def test_find_fair_value_gaps_detects_bearish_gap() -> None:
    candles = [
        make_candle(0, open_=100, high=101, low=99, close=100),
        make_candle(1, open_=100, high=100, low=90, close=91),
        make_candle(2, open_=91, high=95, low=85, close=88),
    ]

    gaps = find_fair_value_gaps(candles)

    assert len(gaps) == 1
    assert gaps[0].direction == "bearish"


def test_analyze_reports_premium_territory_as_opposing_for_bullish_bias() -> None:
    candles = _calm_then_displacement_candles()
    # The final close (140) is near the top of the swing range, so a
    # bullish bias should be flagged as being in unfavorable premium territory.

    report = SmartMoneyAgent().analyze(candles)

    assert any("premium" in note for note in report.opposing_evidence)


def test_find_displacement_index_none_for_too_few_candles() -> None:
    candles = [make_candle(index, open_=100, high=101, low=99, close=100) for index in range(3)]

    assert find_displacement_index(candles) is None


def test_analyze_reports_fair_value_gap_in_supporting_evidence() -> None:
    # Calm candles, then a fair value gap (index 8 -> 10 with no wick
    # overlap), then a large displacement candle to trigger a bias.
    candles = _calm_then_displacement_candles()[:-1]
    candles.append(make_candle(8, open_=100.0, high=101.0, low=100.0, close=100.5))
    candles.append(make_candle(9, open_=100.5, high=110.0, low=100.0, close=109.0))
    candles.append(make_candle(10, open_=109.0, high=160.0, low=115.0, close=155.0))

    report = SmartMoneyAgent().analyze(candles)

    assert report.metrics["fair_value_gap_count"] >= 1
    assert any("fair value gap" in note for note in report.supporting_evidence)


@pytest.mark.parametrize(
    ("position", "bias", "expected_list_name", "expected_fragment"),
    [
        (0.9, "bullish", "opposing", "premium"),
        (0.9, "bearish", "supporting", "premium"),
        (0.1, "bearish", "opposing", "discount"),
        (0.1, "bullish", "supporting", "discount"),
    ],
)
def test_apply_premium_discount_covers_every_bias_combination(
    position: float, bias: str, expected_list_name: str, expected_fragment: str
) -> None:
    supporting: list[str] = []
    opposing: list[str] = []

    SmartMoneyAgent._apply_premium_discount(position, bias, supporting, opposing)  # type: ignore[arg-type]

    target = supporting if expected_list_name == "supporting" else opposing
    other = opposing if expected_list_name == "supporting" else supporting
    assert any(expected_fragment in note for note in target)
    assert other == []
