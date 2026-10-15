"""Unit tests for the dynamic trailing stop / break-even trigger."""

from __future__ import annotations

import pytest

from src.engines.risk_engine.dynamic_stop import (
    DynamicStopInputs,
    compute_dynamic_breakeven_trigger_r_multiple,
    compute_trailing_stop_price,
)

pytestmark = pytest.mark.unit


def test_default_inputs_give_the_base_trigger() -> None:
    trigger = compute_dynamic_breakeven_trigger_r_multiple(DynamicStopInputs(), "buy")

    assert trigger == pytest.approx(1.0)


def test_high_volatility_widens_the_trigger() -> None:
    trigger = compute_dynamic_breakeven_trigger_r_multiple(DynamicStopInputs(atr_ratio=1.5), "buy")

    assert trigger > 1.0


def test_low_volatility_tightens_the_trigger() -> None:
    trigger = compute_dynamic_breakeven_trigger_r_multiple(DynamicStopInputs(atr_ratio=0.5), "buy")

    assert trigger < 1.0


def test_opposing_order_flow_tightens_the_trigger() -> None:
    trigger = compute_dynamic_breakeven_trigger_r_multiple(
        DynamicStopInputs(order_flow_bias="bearish", order_flow_confidence=0.8), "buy"
    )

    assert trigger < 1.0


def test_confirming_htf_trend_widens_the_trigger() -> None:
    trigger = compute_dynamic_breakeven_trigger_r_multiple(
        DynamicStopInputs(htf_trend_bias="bullish"), "buy"
    )

    assert trigger > 1.0


def test_imminent_news_tightens_the_trigger() -> None:
    trigger = compute_dynamic_breakeven_trigger_r_multiple(
        DynamicStopInputs(news_risk_imminent=True), "buy"
    )

    assert trigger < 1.0


def test_choppy_regime_widens_the_trigger() -> None:
    trigger = compute_dynamic_breakeven_trigger_r_multiple(
        DynamicStopInputs(market_regime="range"), "buy"
    )

    assert trigger > 1.0


def test_trigger_is_clamped_to_the_configured_range() -> None:
    extreme_wide = compute_dynamic_breakeven_trigger_r_multiple(
        DynamicStopInputs(atr_ratio=5.0, htf_trend_bias="bullish", market_regime="bull_trend"),
        "buy",
    )
    extreme_tight = compute_dynamic_breakeven_trigger_r_multiple(
        DynamicStopInputs(
            atr_ratio=0.1,
            news_risk_imminent=True,
            order_flow_bias="bearish",
            order_flow_confidence=0.9,
        ),
        "buy",
    )

    assert extreme_wide <= 2.5
    assert extreme_tight >= 0.5


def test_sell_position_uses_opposite_bias_semantics() -> None:
    trigger = compute_dynamic_breakeven_trigger_r_multiple(
        DynamicStopInputs(htf_trend_bias="bearish"), "sell"
    )

    assert trigger > 1.0


def test_trailing_stop_trails_below_price_for_a_buy() -> None:
    stop = compute_trailing_stop_price(
        DynamicStopInputs(), position_direction="buy", current_price=2010.0, risk_distance=10.0
    )

    assert stop < 2010.0


def test_trailing_stop_trails_above_price_for_a_sell() -> None:
    stop = compute_trailing_stop_price(
        DynamicStopInputs(), position_direction="sell", current_price=1990.0, risk_distance=10.0
    )

    assert stop > 1990.0


def test_high_volatility_widens_the_trailing_distance() -> None:
    calm_stop = compute_trailing_stop_price(
        DynamicStopInputs(atr_ratio=1.0),
        position_direction="buy",
        current_price=2010.0,
        risk_distance=10.0,
    )
    volatile_stop = compute_trailing_stop_price(
        DynamicStopInputs(atr_ratio=1.5),
        position_direction="buy",
        current_price=2010.0,
        risk_distance=10.0,
    )

    assert volatile_stop < calm_stop  # further from price = wider trail


def test_nearby_support_floors_the_trailing_stop_for_a_buy() -> None:
    # Without support, the raw trail distance would place the stop at
    # 2010 - 5 = 2005; a support level just below current price should
    # instead floor the stop just beyond that support.
    stop = compute_trailing_stop_price(
        DynamicStopInputs(nearest_support=2008.0),
        position_direction="buy",
        current_price=2010.0,
        risk_distance=10.0,
    )

    assert stop > 2005.0
    assert stop < 2008.0


def test_distant_support_does_not_affect_the_trailing_stop() -> None:
    with_distant_support = compute_trailing_stop_price(
        DynamicStopInputs(nearest_support=1900.0),
        position_direction="buy",
        current_price=2010.0,
        risk_distance=10.0,
    )
    without_support = compute_trailing_stop_price(
        DynamicStopInputs(),
        position_direction="buy",
        current_price=2010.0,
        risk_distance=10.0,
    )

    assert with_distant_support == pytest.approx(without_support)


def test_imminent_news_tightens_the_trailing_distance() -> None:
    calm_stop = compute_trailing_stop_price(
        DynamicStopInputs(),
        position_direction="buy",
        current_price=2010.0,
        risk_distance=10.0,
    )
    news_stop = compute_trailing_stop_price(
        DynamicStopInputs(news_risk_imminent=True),
        position_direction="buy",
        current_price=2010.0,
        risk_distance=10.0,
    )

    assert news_stop > calm_stop  # tighter trail = closer to price


def test_nearby_resistance_caps_the_trailing_stop_for_a_sell() -> None:
    stop = compute_trailing_stop_price(
        DynamicStopInputs(nearest_resistance=1992.0),
        position_direction="sell",
        current_price=1990.0,
        risk_distance=10.0,
    )

    assert stop < 1995.0
    assert stop > 1992.0
