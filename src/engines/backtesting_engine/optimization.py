"""Parameter grid search for the Backtesting Engine.

Per BACKTESTING_ENGINE.md "Parameter Testing": "Never optimize only for
maximum profit. Optimize for robustness." Ranks parameter combinations by
a robustness score that penalizes drawdown, rather than by raw profit alone.
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

_DRAWDOWN_PENALTY_WEIGHT = 0.02


@dataclass(frozen=True, slots=True)
class ParameterCombination:
    """One stop-loss/take-profit parameter pair to evaluate."""

    stop_loss_pct: float
    take_profit_pct: float | None


@dataclass(frozen=True, slots=True)
class OptimizationResult:
    """One parameter combination's backtest report and robustness score."""

    parameters: ParameterCombination
    report: BacktestReport
    robustness_score: float


def _robustness_score(report: BacktestReport) -> float:
    """Profit factor penalized by drawdown, per "optimize for robustness"."""
    profit_factor = report.profit_factor
    if profit_factor == float("inf"):
        profit_factor = report.expectancy_pct
    return profit_factor - report.max_drawdown_pct * _DRAWDOWN_PENALTY_WEIGHT


def run_parameter_grid_search(
    candles: list[Candle],
    signal_function: SignalFunction,
    *,
    window_size: int,
    parameter_combinations: list[ParameterCombination],
    strategy_name: str,
    strategy_version: str,
    execution_costs: ExecutionCosts | None = None,
) -> list[OptimizationResult]:
    """Backtest every parameter combination and rank by robustness score.

    Args:
        candles: Candle series to backtest against.
        signal_function: Signal generator, as in `run_historical_replay`.
        window_size: Candles per signal-generation window.
        parameter_combinations: Stop-loss/take-profit pairs to evaluate.
        strategy_name: Name of the tested strategy.
        strategy_version: Version tag of the tested strategy.
        execution_costs: Spread/slippage/commission assumptions.

    Returns:
        One `OptimizationResult` per combination, ranked by
        `robustness_score` descending — profit factor penalized by
        drawdown, never raw profit alone.
    """
    results = []
    for parameters in parameter_combinations:
        run = run_historical_replay(
            candles,
            signal_function,
            window_size=window_size,
            stop_loss_pct=parameters.stop_loss_pct,
            take_profit_pct=parameters.take_profit_pct,
            execution_costs=execution_costs,
        )
        report = build_report(run, strategy_name=strategy_name, strategy_version=strategy_version)
        results.append(
            OptimizationResult(
                parameters=parameters, report=report, robustness_score=_robustness_score(report)
            )
        )

    results.sort(key=lambda result: result.robustness_score, reverse=True)
    return results
