"""Historical replay simulation for the Backtesting Engine.

Per BACKTESTING_ENGINE.md "Core Principles": "Backtests must be
reproducible... deterministic... use historical data only. No future
information may leak into the past." Every simulated trade's signal is
computed strictly from candles *before* its entry bar and executes at
that *same* bar's open on the following iteration — never using a bar's
own high/low/close to decide whether to enter it.

A bar-by-bar ("Bar Replay") simulation is used rather than tick replay,
since no engine in this platform collects tick-level history yet
(MT5_ENGINE.md "Market Data": ticks are a documented future data source).
When a bar's high and low both cross the stop and target in the same bar,
the true intrabar order is unknowable without tick data, so the stop is
conservatively assumed to trigger first.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from src.models.candle import Candle

Signal = Literal["buy", "sell", "wait"]
SignalFunction = Callable[[list[Candle]], Signal]
ExitReason = Literal["stop_loss", "take_profit", "signal_reversed", "end_of_data"]


@dataclass(frozen=True, slots=True)
class ExecutionCosts:
    """Per-trade execution cost assumptions (BACKTESTING_ENGINE.md "Execution Simulation").

    Attributes:
        spread_pct: Bid/ask spread cost, as a percentage of entry price.
        slippage_pct: Extra adverse price movement on fill, as a percentage.
        commission_pct: Broker commission, as a percentage of position value.
    """

    spread_pct: float = 0.0
    slippage_pct: float = 0.0
    commission_pct: float = 0.0

    @property
    def total_cost_pct(self) -> float:
        """Total one-way cost, as a percentage of the fill price."""
        return self.spread_pct + self.slippage_pct + self.commission_pct


@dataclass(frozen=True, slots=True)
class SimulatedTrade:
    """One completed simulated trade.

    Attributes:
        direction: "buy" or "sell".
        entry_timestamp: When the trade was entered.
        entry_price: Simulated entry price, net of `ExecutionCosts`.
        exit_timestamp: When the trade was exited.
        exit_price: Simulated exit price, net of `ExecutionCosts`.
        exit_reason: Why the trade closed.
        return_pct: Realized return, in percent, net of execution costs.
    """

    direction: Literal["buy", "sell"]
    entry_timestamp: datetime
    entry_price: float
    exit_timestamp: datetime
    exit_price: float
    exit_reason: ExitReason
    return_pct: float


@dataclass(frozen=True, slots=True)
class BacktestRun:
    """The full output of one historical replay.

    Attributes:
        trades: Every completed simulated trade, in chronological order.
        equity_curve: Cumulative equity, starting equity first, then after
            each closed trade.
    """

    trades: list[SimulatedTrade]
    equity_curve: list[float]


@dataclass(frozen=True, slots=True)
class _OpenPosition:
    direction: Literal["buy", "sell"]
    entry_timestamp: datetime
    entry_price: float
    stop_loss: float
    take_profit: float | None


_PRICE_PRECISION = 8  # rounds away binary floating-point noise (e.g. 100*1.1 = 110.00000000000001),
# far below any realistic instrument's actual price precision.


def _apply_entry_costs(
    direction: Literal["buy", "sell"], price: float, costs: ExecutionCosts
) -> float:
    cost_multiplier = 1 + (costs.total_cost_pct / 100)
    result = price * cost_multiplier if direction == "buy" else price / cost_multiplier
    return round(result, _PRICE_PRECISION)


def _apply_exit_costs(
    direction: Literal["buy", "sell"], price: float, costs: ExecutionCosts
) -> float:
    cost_multiplier = 1 + (costs.total_cost_pct / 100)
    result = price / cost_multiplier if direction == "buy" else price * cost_multiplier
    return round(result, _PRICE_PRECISION)


def _stop_price(
    direction: Literal["buy", "sell"], entry_price: float, stop_loss_pct: float
) -> float:
    result = (
        entry_price * (1 - stop_loss_pct / 100)
        if direction == "buy"
        else entry_price * (1 + stop_loss_pct / 100)
    )
    return round(result, _PRICE_PRECISION)


def _target_price(
    direction: Literal["buy", "sell"], entry_price: float, take_profit_pct: float
) -> float:
    result = (
        entry_price * (1 + take_profit_pct / 100)
        if direction == "buy"
        else entry_price * (1 - take_profit_pct / 100)
    )
    return round(result, _PRICE_PRECISION)


def _check_stop_or_target(position: _OpenPosition, bar: Candle) -> tuple[float, ExitReason] | None:
    if position.direction == "buy":
        if bar.low <= position.stop_loss:
            return position.stop_loss, "stop_loss"
        if position.take_profit is not None and bar.high >= position.take_profit:
            return position.take_profit, "take_profit"
    else:
        if bar.high >= position.stop_loss:
            return position.stop_loss, "stop_loss"
        if position.take_profit is not None and bar.low <= position.take_profit:
            return position.take_profit, "take_profit"
    return None


def _close_position(
    position: _OpenPosition,
    exit_timestamp: datetime,
    raw_exit_price: float,
    exit_reason: ExitReason,
    costs: ExecutionCosts,
) -> SimulatedTrade:
    exit_price = _apply_exit_costs(position.direction, raw_exit_price, costs)
    direction_sign = 1 if position.direction == "buy" else -1
    return_pct = (
        (exit_price - position.entry_price) / position.entry_price * 100 * direction_sign
    )
    return SimulatedTrade(
        direction=position.direction,
        entry_timestamp=position.entry_timestamp,
        entry_price=position.entry_price,
        exit_timestamp=exit_timestamp,
        exit_price=exit_price,
        exit_reason=exit_reason,
        return_pct=return_pct,
    )


def run_historical_replay(
    candles: list[Candle],
    signal_function: SignalFunction,
    *,
    window_size: int,
    stop_loss_pct: float,
    take_profit_pct: float | None = None,
    execution_costs: ExecutionCosts | None = None,
    starting_equity: float = 10_000.0,
) -> BacktestRun:
    """Replay a candle series bar-by-bar, simulating one position at a time.

    Args:
        candles: Candles ordered by timestamp ascending.
        signal_function: Computes a `Signal` from a rolling window of
            candles ending at the bar *before* the current one — never
            including the bar being decided on.
        window_size: Number of candles the signal function sees.
        stop_loss_pct: Protective stop distance, as a percentage of entry price.
        take_profit_pct: Target distance, as a percentage of entry price;
            None disables the target (exits only on stop or signal reversal).
        execution_costs: Spread/slippage/commission assumptions; defaults
            to zero cost (an idealized fill).
        starting_equity: Initial simulated account equity.

    Returns:
        A `BacktestRun` with every completed trade and the resulting
        equity curve. Empty if `candles` has fewer than `window_size + 1` bars.
    """
    costs = execution_costs or ExecutionCosts()
    equity = starting_equity
    equity_curve = [equity]
    trades: list[SimulatedTrade] = []
    position: _OpenPosition | None = None

    for index in range(window_size, len(candles)):
        window = candles[index - window_size : index]
        bar = candles[index]
        signal = signal_function(window)

        exit_result: tuple[float, ExitReason] | None = None
        if position is not None:
            exit_result = _check_stop_or_target(position, bar)
            if exit_result is None and signal in ("buy", "sell") and signal != position.direction:
                exit_result = (bar.open, "signal_reversed")

        if position is not None and exit_result is not None:
            raw_exit_price, exit_reason = exit_result
            trade = _close_position(position, bar.timestamp, raw_exit_price, exit_reason, costs)
            trades.append(trade)
            equity *= 1 + trade.return_pct / 100
            equity_curve.append(equity)
            position = None

        # A same-bar flip: after a signal-reversal close above, an opposing
        # signal immediately opens the new position at the same bar's open,
        # rather than waiting a bar flat.
        if position is None and signal in ("buy", "sell"):
            entry_price = _apply_entry_costs(signal, bar.open, costs)
            position = _OpenPosition(
                direction=signal,
                entry_timestamp=bar.timestamp,
                entry_price=entry_price,
                stop_loss=_stop_price(signal, entry_price, stop_loss_pct),
                take_profit=(
                    _target_price(signal, entry_price, take_profit_pct)
                    if take_profit_pct is not None
                    else None
                ),
            )

    if position is not None:
        last_bar = candles[-1]
        trade = _close_position(position, last_bar.timestamp, last_bar.close, "end_of_data", costs)
        trades.append(trade)
        equity *= 1 + trade.return_pct / 100
        equity_curve.append(equity)

    return BacktestRun(trades=trades, equity_curve=equity_curve)
