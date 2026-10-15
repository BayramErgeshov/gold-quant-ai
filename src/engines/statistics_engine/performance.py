"""Trading performance statistics for the Statistics Engine.

Per MACHINE_LEARNING_ENGINE.md "Performance Metrics": classic, well-defined
formulas computed over a sequence of realized trade/period returns.
Populated once real (paper or live) trades exist — Phase 13's Execution
Engine and Phase 15's Backtesting Engine are the producers of that data;
these functions never fabricate a track record from no data.
"""

from __future__ import annotations

import math

_TRADING_DAYS_PER_YEAR = 252
_MIN_OBSERVATIONS_FOR_STDDEV = 2


def win_rate(returns_pct: list[float]) -> float:
    """Fraction of trades with a strictly positive return.

    Args:
        returns_pct: Realized return per closed trade, in percent.

    Returns:
        Win rate in [0.0, 1.0]. 0.0 if `returns_pct` is empty.
    """
    if not returns_pct:
        return 0.0
    return sum(1 for value in returns_pct if value > 0) / len(returns_pct)


def profit_factor(returns_pct: list[float]) -> float:
    """Ratio of gross profit to gross loss.

    Args:
        returns_pct: Realized return per closed trade, in percent.

    Returns:
        Gross profit / gross loss. `math.inf` if there are wins and no
        losses; 0.0 if there are no wins at all (including an empty list).
    """
    gross_profit = sum(value for value in returns_pct if value > 0)
    gross_loss = -sum(value for value in returns_pct if value < 0)
    if gross_loss == 0:
        return math.inf if gross_profit > 0 else 0.0
    return gross_profit / gross_loss


def expectancy_pct(returns_pct: list[float]) -> float:
    """Average return per trade.

    Args:
        returns_pct: Realized return per closed trade, in percent.

    Returns:
        The mean return, in percent. 0.0 if `returns_pct` is empty.
    """
    if not returns_pct:
        return 0.0
    return sum(returns_pct) / len(returns_pct)


def sharpe_ratio(
    returns_pct: list[float], *, periods_per_year: int = _TRADING_DAYS_PER_YEAR
) -> float:
    """Annualized Sharpe ratio (assumes a 0% risk-free rate).

    Args:
        returns_pct: Realized return per period, in percent.
        periods_per_year: Number of periods per year, for annualization.

    Returns:
        The annualized Sharpe ratio. 0.0 if fewer than two returns or the
        standard deviation is 0.
    """
    if len(returns_pct) < _MIN_OBSERVATIONS_FOR_STDDEV:
        return 0.0
    mean_return = sum(returns_pct) / len(returns_pct)
    variance = sum((value - mean_return) ** 2 for value in returns_pct) / (len(returns_pct) - 1)
    stddev = math.sqrt(variance)
    if stddev == 0:
        return 0.0
    return (mean_return / stddev) * math.sqrt(periods_per_year)


def sortino_ratio(
    returns_pct: list[float], *, periods_per_year: int = _TRADING_DAYS_PER_YEAR
) -> float:
    """Annualized Sortino ratio (downside deviation only, 0% risk-free rate).

    Args:
        returns_pct: Realized return per period, in percent.
        periods_per_year: Number of periods per year, for annualization.

    Returns:
        The annualized Sortino ratio. 0.0 if fewer than two returns or
        there is no downside deviation (no losing periods).
    """
    if len(returns_pct) < _MIN_OBSERVATIONS_FOR_STDDEV:
        return 0.0
    mean_return = sum(returns_pct) / len(returns_pct)
    downside = [min(0.0, value) for value in returns_pct]
    downside_variance = sum(value**2 for value in downside) / len(downside)
    downside_deviation = math.sqrt(downside_variance)
    if downside_deviation == 0:
        return 0.0
    return (mean_return / downside_deviation) * math.sqrt(periods_per_year)


def max_drawdown_pct(equity_curve: list[float]) -> float:
    """Largest peak-to-trough decline in an equity curve.

    Args:
        equity_curve: Cumulative account equity/balance over time, in any
            consistent unit, ordered chronologically.

    Returns:
        The maximum drawdown as a positive percentage. 0.0 if
        `equity_curve` has fewer than two points.
    """
    if len(equity_curve) < _MIN_OBSERVATIONS_FOR_STDDEV:
        return 0.0

    peak = equity_curve[0]
    max_drawdown = 0.0
    for value in equity_curve:
        peak = max(peak, value)
        if peak > 0:
            drawdown = (peak - value) / peak * 100
            max_drawdown = max(max_drawdown, drawdown)
    return max_drawdown


def average_win_pct(returns_pct: list[float]) -> float:
    """Average return of winning trades only.

    Args:
        returns_pct: Realized return per closed trade, in percent.

    Returns:
        Mean return across trades with a strictly positive return, in
        percent. 0.0 if there are no winning trades.
    """
    wins = [value for value in returns_pct if value > 0]
    return sum(wins) / len(wins) if wins else 0.0


def average_loss_pct(returns_pct: list[float]) -> float:
    """Average loss magnitude of losing trades only.

    Args:
        returns_pct: Realized return per closed trade, in percent.

    Returns:
        Mean loss magnitude across trades with a strictly negative
        return, in percent, as a positive number (a loss size, not a
        negative return). 0.0 if there are no losing trades.
    """
    losses = [-value for value in returns_pct if value < 0]
    return sum(losses) / len(losses) if losses else 0.0


def max_consecutive_wins(returns_pct: list[float]) -> int:
    """Longest streak of consecutive winning trades, in chronological order.

    Args:
        returns_pct: Realized return per closed trade, in percent, in
            chronological (closing) order.

    Returns:
        The longest run of strictly positive returns. 0 if there are none.
    """
    longest = current = 0
    for value in returns_pct:
        current = current + 1 if value > 0 else 0
        longest = max(longest, current)
    return longest


def max_consecutive_losses(returns_pct: list[float]) -> int:
    """Longest streak of consecutive losing trades, in chronological order.

    Args:
        returns_pct: Realized return per closed trade, in percent, in
            chronological (closing) order.

    Returns:
        The longest run of strictly negative returns. 0 if there are none.
    """
    longest = current = 0
    for value in returns_pct:
        current = current + 1 if value < 0 else 0
        longest = max(longest, current)
    return longest


def calmar_ratio(*, total_return_pct: float, max_drawdown_pct: float, days_covered: float) -> float:
    """Annualized return divided by max drawdown, over an actual calendar period.

    Unlike `sharpe_ratio`/`sortino_ratio` (which assume evenly-spaced
    periods), trades are not evenly spaced in time, so annualization here
    uses the actual number of calendar days the trade sequence spans
    rather than a fixed periods-per-year assumption.

    Args:
        total_return_pct: Total realized return over the period, in percent.
        max_drawdown_pct: The period's maximum drawdown, as a positive percentage.
        days_covered: Actual calendar days between the first and last trade.

    Returns:
        The Calmar ratio. 0.0 if `max_drawdown_pct` or `days_covered` is
        not strictly positive — never a fabricated ratio from an
        undefined or zero-length period.
    """
    if max_drawdown_pct <= 0 or days_covered <= 0:
        return 0.0
    annualized_return_pct = total_return_pct * (365.25 / days_covered)
    return annualized_return_pct / max_drawdown_pct


def recovery_factor(*, net_profit: float, max_drawdown: float) -> float:
    """Net profit divided by max drawdown, in matching units (both $ or both %).

    Args:
        net_profit: Total realized profit/loss over the period.
        max_drawdown: The period's maximum drawdown, as a positive
            magnitude, in the same unit as `net_profit`.

    Returns:
        The recovery factor. 0.0 if `max_drawdown` is not strictly
        positive — never a fabricated infinite recovery factor.
    """
    if max_drawdown <= 0:
        return 0.0
    return net_profit / max_drawdown
