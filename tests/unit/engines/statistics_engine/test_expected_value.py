"""Unit tests for expected value calculation."""

from __future__ import annotations

import pytest

from src.engines.statistics_engine.expected_value import compute_expected_value

pytestmark = pytest.mark.unit


def test_positive_expected_value_for_favorable_setup() -> None:
    ev = compute_expected_value(win_probability=0.6, average_win_pct=2.0, average_loss_pct=1.0)

    assert ev == pytest.approx(0.6 * 2.0 - 0.4 * 1.0)
    assert ev > 0


def test_negative_expected_value_for_unfavorable_setup() -> None:
    ev = compute_expected_value(win_probability=0.3, average_win_pct=1.0, average_loss_pct=2.0)

    assert ev < 0


def test_zero_expected_value_at_breakeven() -> None:
    ev = compute_expected_value(win_probability=0.5, average_win_pct=1.0, average_loss_pct=1.0)

    assert ev == pytest.approx(0.0)
