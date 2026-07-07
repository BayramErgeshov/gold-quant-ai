"""Unit tests for Monte Carlo trade-order randomization."""

from __future__ import annotations

import pytest

from src.engines.backtesting_engine.monte_carlo import run_monte_carlo

pytestmark = pytest.mark.unit


def test_returns_all_zero_for_empty_returns() -> None:
    result = run_monte_carlo([])

    assert result.final_equity_p05 == 0.0
    assert result.final_equity_p50 == 0.0
    assert result.final_equity_p95 == 0.0
    assert result.max_drawdown_p50 == 0.0
    assert result.max_drawdown_p95 == 0.0


def test_is_reproducible_with_a_fixed_seed() -> None:
    returns = [2.0, -1.0, 3.0, -0.5, 1.5]

    first = run_monte_carlo(returns, n_simulations=200, seed=42)
    second = run_monte_carlo(returns, n_simulations=200, seed=42)

    assert first == second


def test_percentiles_are_ordered() -> None:
    returns = [2.0, -1.0, 3.0, -0.5, 1.5, -2.0, 4.0]

    result = run_monte_carlo(returns, n_simulations=500, seed=1)

    assert result.final_equity_p05 <= result.final_equity_p50 <= result.final_equity_p95
    assert result.max_drawdown_p50 <= result.max_drawdown_p95


def test_all_positive_returns_grow_equity_in_every_percentile() -> None:
    returns = [1.0, 2.0, 1.5, 3.0]

    result = run_monte_carlo(returns, starting_equity=10_000.0, n_simulations=300, seed=7)

    assert result.final_equity_p05 > 10_000.0
    assert result.final_equity_p50 > 10_000.0
    assert result.final_equity_p95 > 10_000.0


def test_different_seeds_can_produce_different_results() -> None:
    returns = [5.0, -4.0, 3.0, -2.0, 6.0, -5.0]

    first = run_monte_carlo(returns, n_simulations=50, seed=1)
    second = run_monte_carlo(returns, n_simulations=50, seed=2)

    assert first != second
