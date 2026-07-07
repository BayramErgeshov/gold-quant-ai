"""Walk-forward validation for the Backtesting Engine.

Per BACKTESTING_ENGINE.md "Walk Forward": "Split Training Data ->
Validation Data -> Out-of-Sample Data -> Forward Simulation. Only
strategies passing every stage continue." Splits a candle series into
consecutive, non-overlapping windows and runs the simulator independently
on each — each window's signal function sees only candles up to its own
point in time, so no window's result can leak into another's.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.engines.backtesting_engine.report import BacktestReport, build_report
from src.engines.backtesting_engine.simulator import (
    ExecutionCosts,
    SignalFunction,
    run_historical_replay,
)
from src.models.candle import Candle


@dataclass(frozen=True, slots=True)
class WalkForwardResult:
    """The outcome of walk-forward validation.

    Attributes:
        window_reports: One `BacktestReport` per consecutive window, in order.
        passed: True only if every window met the pass criteria
            (BACKTESTING_ENGINE.md: "Only strategies passing every stage continue").
    """

    window_reports: list[BacktestReport]
    passed: bool


def run_walk_forward(
    candles: list[Candle],
    signal_function: SignalFunction,
    *,
    window_size: int,
    stop_loss_pct: float,
    take_profit_pct: float | None,
    n_windows: int,
    strategy_name: str,
    strategy_version: str,
    execution_costs: ExecutionCosts | None = None,
    min_win_rate: float = 0.0,
    min_profit_factor: float = 0.0,
) -> WalkForwardResult:
    """Split candles into `n_windows` consecutive slices and backtest each.

    Args:
        candles: Full candle series, ordered by timestamp ascending.
        signal_function: Signal generator, as in `run_historical_replay`.
        window_size: Candles per signal-generation window.
        stop_loss_pct: Protective stop distance, in percent.
        take_profit_pct: Target distance, in percent, or None.
        n_windows: Number of consecutive slices to test.
        strategy_name: Name of the tested strategy.
        strategy_version: Version tag of the tested strategy.
        execution_costs: Spread/slippage/commission assumptions.
        min_win_rate: Minimum win rate a window must achieve to "pass".
        min_profit_factor: Minimum profit factor a window must achieve to "pass".

    Returns:
        A `WalkForwardResult`. `passed` is only True if every window met
        both minimums — one weak window fails the whole validation.

    Raises:
        ValueError: If `n_windows` is not positive.
    """
    if n_windows <= 0:
        raise ValueError("n_windows must be positive")

    slice_size = len(candles) // n_windows
    reports: list[BacktestReport] = []

    for window_index in range(n_windows):
        start = window_index * slice_size
        end = len(candles) if window_index == n_windows - 1 else start + slice_size
        window_candles = candles[start:end]

        run = run_historical_replay(
            window_candles,
            signal_function,
            window_size=window_size,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
            execution_costs=execution_costs,
        )
        reports.append(
            build_report(
                run,
                strategy_name=strategy_name,
                strategy_version=f"{strategy_version}-window{window_index + 1}",
            )
        )

    passed = all(
        report.win_rate >= min_win_rate and report.profit_factor >= min_profit_factor
        for report in reports
    )
    return WalkForwardResult(window_reports=reports, passed=passed)
