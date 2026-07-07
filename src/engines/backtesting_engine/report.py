"""Backtest report generation.

Per BACKTESTING_ENGINE.md "Report": "Every completed backtest generates
Strategy Name, Version, Period Tested, Trades, Win Rate, Profit Factor,
Sharpe, Sortino, Drawdown, Expectancy..." Quantitative fields are computed
here by reusing Phase 10's `statistics_engine.performance`; qualitative
fields (Strengths, Weaknesses, Failure Conditions, Recommended
Improvements, Production Recommendation) require human or Chief AI
judgment and are supplied by the caller rather than fabricated.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.engines.backtesting_engine.simulator import BacktestRun
from src.engines.statistics_engine.performance import (
    expectancy_pct,
    max_drawdown_pct,
    profit_factor,
    sharpe_ratio,
    sortino_ratio,
    win_rate,
)


@dataclass(frozen=True, slots=True)
class BacktestReport:
    """Quantitative summary of one completed backtest run.

    Attributes:
        strategy_name: Name of the tested strategy.
        strategy_version: Version tag of the tested strategy.
        trade_count: Number of completed trades.
        win_rate: Fraction of trades with a positive return.
        profit_factor: Gross profit / gross loss.
        sharpe_ratio: Annualized Sharpe ratio over trade returns.
        sortino_ratio: Annualized Sortino ratio over trade returns.
        max_drawdown_pct: Largest peak-to-trough equity decline, in percent.
        expectancy_pct: Average return per trade, in percent.
        final_equity: Simulated equity at the end of the run.
        strengths: Caller-supplied observed strengths, if any.
        weaknesses: Caller-supplied observed weaknesses, if any.
    """

    strategy_name: str
    strategy_version: str
    trade_count: int
    win_rate: float
    profit_factor: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown_pct: float
    expectancy_pct: float
    final_equity: float
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)


def build_report(
    run: BacktestRun,
    *,
    strategy_name: str,
    strategy_version: str,
    strengths: list[str] | None = None,
    weaknesses: list[str] | None = None,
) -> BacktestReport:
    """Build a `BacktestReport` from a completed `BacktestRun`.

    Args:
        run: The completed historical replay.
        strategy_name: Name of the tested strategy.
        strategy_version: Version tag of the tested strategy.
        strengths: Human/Chief-AI-supplied observed strengths, if any.
        weaknesses: Human/Chief-AI-supplied observed weaknesses, if any.

    Returns:
        A `BacktestReport` with every quantitative field computed from `run`.
    """
    returns = [trade.return_pct for trade in run.trades]
    return BacktestReport(
        strategy_name=strategy_name,
        strategy_version=strategy_version,
        trade_count=len(run.trades),
        win_rate=win_rate(returns),
        profit_factor=profit_factor(returns),
        sharpe_ratio=sharpe_ratio(returns),
        sortino_ratio=sortino_ratio(returns),
        max_drawdown_pct=max_drawdown_pct(run.equity_curve),
        expectancy_pct=expectancy_pct(returns),
        final_equity=run.equity_curve[-1] if run.equity_curve else 0.0,
        strengths=strengths or [],
        weaknesses=weaknesses or [],
    )
