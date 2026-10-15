"""Unit tests for dynamic position sizing."""

from __future__ import annotations

import pytest

from src.engines.risk_engine.position_sizing import (
    compute_drawdown_scaling_factor,
    compute_fixed_lot_position_size,
    compute_position_size,
)

pytestmark = pytest.mark.unit


def test_scaling_factor_is_one_at_zero_drawdown() -> None:
    assert compute_drawdown_scaling_factor(0.0) == 1.0


def test_scaling_factor_is_one_for_negative_drawdown() -> None:
    assert compute_drawdown_scaling_factor(-5.0) == 1.0


def test_scaling_factor_is_zero_at_max_drawdown() -> None:
    assert compute_drawdown_scaling_factor(20.0, max_drawdown_for_zero_risk_pct=20.0) == 0.0


def test_scaling_factor_is_zero_beyond_max_drawdown() -> None:
    assert compute_drawdown_scaling_factor(30.0, max_drawdown_for_zero_risk_pct=20.0) == 0.0


def test_scaling_factor_decreases_linearly() -> None:
    assert compute_drawdown_scaling_factor(
        10.0, max_drawdown_for_zero_risk_pct=20.0
    ) == pytest.approx(0.5)


def test_position_size_raises_for_non_positive_risk_pct() -> None:
    with pytest.raises(ValueError, match="risk_per_trade_pct"):
        compute_position_size(
            account_equity=10_000,
            risk_per_trade_pct=0.0,
            entry_price=2000.0,
            stop_loss_price=1990.0,
        )


def test_position_size_is_zero_for_equal_entry_and_stop() -> None:
    result = compute_position_size(
        account_equity=10_000,
        risk_per_trade_pct=1.0,
        entry_price=2000.0,
        stop_loss_price=2000.0,
    )

    assert result.position_size_units == 0.0


def test_position_size_is_zero_for_non_positive_equity() -> None:
    result = compute_position_size(
        account_equity=0.0,
        risk_per_trade_pct=1.0,
        entry_price=2000.0,
        stop_loss_price=1990.0,
    )

    assert result.position_size_units == 0.0


def test_position_size_computes_expected_units() -> None:
    result = compute_position_size(
        account_equity=10_000,
        risk_per_trade_pct=1.0,
        entry_price=2000.0,
        stop_loss_price=1990.0,
    )

    # risk_amount = 10_000 * 1% = 100; stop_distance = 10 -> 10 units.
    assert result.risk_amount == pytest.approx(100.0)
    assert result.position_size_units == pytest.approx(10.0)
    assert result.effective_risk_pct == pytest.approx(1.0)


def test_position_size_scales_down_after_drawdown() -> None:
    result = compute_position_size(
        account_equity=10_000,
        risk_per_trade_pct=1.0,
        entry_price=2000.0,
        stop_loss_price=1990.0,
        current_drawdown_pct=10.0,
    )

    assert result.effective_risk_pct < 1.0
    assert result.position_size_units < 10.0


def test_position_size_respects_max_position_value_cap() -> None:
    result = compute_position_size(
        account_equity=1_000_000,
        risk_per_trade_pct=1.0,
        entry_price=2000.0,
        stop_loss_price=1990.0,
        max_position_value=20_000.0,
    )

    assert result.position_size_units == pytest.approx(10.0)


def test_fixed_lot_position_size_raises_for_non_positive_size() -> None:
    with pytest.raises(ValueError, match="fixed_lot_size"):
        compute_fixed_lot_position_size(
            fixed_lot_size=0.0,
            account_equity=10_000,
            entry_price=2000.0,
            stop_loss_price=1990.0,
        )


def test_fixed_lot_position_size_always_returns_the_configured_size() -> None:
    high_confidence_setup = compute_fixed_lot_position_size(
        fixed_lot_size=5.0, account_equity=10_000, entry_price=2000.0, stop_loss_price=1990.0
    )
    different_stop_distance = compute_fixed_lot_position_size(
        fixed_lot_size=5.0, account_equity=10_000, entry_price=2000.0, stop_loss_price=1950.0
    )

    # Neither the stop distance nor anything about the setup changes the
    # returned size -- it is always exactly the user's configured value.
    assert high_confidence_setup.position_size_units == pytest.approx(5.0)
    assert different_stop_distance.position_size_units == pytest.approx(5.0)


def test_fixed_lot_position_size_scales_down_after_drawdown() -> None:
    result = compute_fixed_lot_position_size(
        fixed_lot_size=5.0,
        account_equity=10_000,
        entry_price=2000.0,
        stop_loss_price=1990.0,
        current_drawdown_pct=10.0,
    )

    assert result.position_size_units < 5.0


def test_fixed_lot_position_size_reports_informational_risk_pct() -> None:
    result = compute_fixed_lot_position_size(
        fixed_lot_size=5.0, account_equity=10_000, entry_price=2000.0, stop_loss_price=1990.0
    )

    # risk_amount = 5 units * 10 stop distance = 50; 50 / 10_000 = 0.5%.
    assert result.risk_amount == pytest.approx(50.0)
    assert result.effective_risk_pct == pytest.approx(0.5)


def test_fixed_lot_position_size_zero_risk_pct_for_non_positive_equity() -> None:
    result = compute_fixed_lot_position_size(
        fixed_lot_size=5.0, account_equity=0.0, entry_price=2000.0, stop_loss_price=1990.0
    )

    assert result.position_size_units == pytest.approx(5.0)
    assert result.effective_risk_pct == 0.0
