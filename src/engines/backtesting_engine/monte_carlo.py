"""Monte Carlo trade-order randomization for the Backtesting Engine.

Per BACKTESTING_ENGINE.md "Monte Carlo": "Randomize Trade Order... Measure
Stability, Drawdown, Risk, Confidence." Resamples a completed backtest's
trade returns with replacement to build a distribution of possible equity
outcomes, rather than trusting the single realized trade order.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from src.engines.statistics_engine.performance import max_drawdown_pct

_DEFAULT_SIMULATIONS = 1000


@dataclass(frozen=True, slots=True)
class MonteCarloResult:
    """Distribution summary across randomized trade-order simulations.

    Attributes:
        final_equity_p05: 5th percentile final equity across simulations.
        final_equity_p50: Median final equity across simulations.
        final_equity_p95: 95th percentile final equity across simulations.
        max_drawdown_p50: Median max drawdown percentage across simulations.
        max_drawdown_p95: 95th percentile (worst-tail) max drawdown percentage.
    """

    final_equity_p05: float
    final_equity_p50: float
    final_equity_p95: float
    max_drawdown_p50: float
    max_drawdown_p95: float


def _percentile(sorted_values: list[float], fraction: float) -> float:
    index = min(int(fraction * len(sorted_values)), len(sorted_values) - 1)
    return sorted_values[index]


def run_monte_carlo(
    returns_pct: list[float],
    *,
    starting_equity: float = 10_000.0,
    n_simulations: int = _DEFAULT_SIMULATIONS,
    seed: int | None = None,
) -> MonteCarloResult:
    """Resample trade order with replacement and summarize the outcome distribution.

    Args:
        returns_pct: Realized returns from one completed backtest, in
            percent, in their original chronological order.
        starting_equity: Initial simulated account equity for each resample.
        n_simulations: Number of randomized resamples to run.
        seed: Optional random seed, for reproducible results
            (BACKTESTING_ENGINE.md "Core Principles": "Backtests must be reproducible").

    Returns:
        A `MonteCarloResult` summarizing the distribution of outcomes.
        All zero if `returns_pct` is empty — never a fabricated distribution.
    """
    if not returns_pct:
        return MonteCarloResult(
            final_equity_p05=0.0,
            final_equity_p50=0.0,
            final_equity_p95=0.0,
            max_drawdown_p50=0.0,
            max_drawdown_p95=0.0,
        )

    rng = random.Random(seed)
    final_equities: list[float] = []
    max_drawdowns: list[float] = []

    for _ in range(n_simulations):
        resampled = rng.choices(returns_pct, k=len(returns_pct))
        equity_curve = [starting_equity]
        for return_pct in resampled:
            equity_curve.append(equity_curve[-1] * (1 + return_pct / 100))
        final_equities.append(equity_curve[-1])
        max_drawdowns.append(max_drawdown_pct(equity_curve))

    final_equities.sort()
    max_drawdowns.sort()

    return MonteCarloResult(
        final_equity_p05=_percentile(final_equities, 0.05),
        final_equity_p50=_percentile(final_equities, 0.50),
        final_equity_p95=_percentile(final_equities, 0.95),
        max_drawdown_p50=_percentile(max_drawdowns, 0.50),
        max_drawdown_p95=_percentile(max_drawdowns, 0.95),
    )
