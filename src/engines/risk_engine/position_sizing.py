"""Dynamic position sizing for the Risk Engine.

Per RISK_ENGINE.md "Position Sizing": "The Risk Engine calculates position
size dynamically... Position size must never be fixed." Sizes every trade
from account equity and the distance to its invalidation level (never a
fixed pip/point distance), scaled down as drawdown increases (RISK_ENGINE.md
"Risk Philosophy": "Never increase risk after losses").
"""

from __future__ import annotations

from dataclasses import dataclass

_DEFAULT_MAX_DRAWDOWN_FOR_ZERO_RISK_PCT = 20.0


@dataclass(frozen=True, slots=True)
class PositionSizeResult:
    """The computed position size and the inputs that produced it.

    Attributes:
        position_size_units: Recommended position size, in the same unit
            as `entry_price`/`stop_loss_price` (e.g. ounces for XAUUSD).
        risk_amount: Account currency amount risked if the stop is hit.
        effective_risk_pct: The risk percentage actually applied, after
            drawdown scaling.
    """

    position_size_units: float
    risk_amount: float
    effective_risk_pct: float


def compute_drawdown_scaling_factor(
    current_drawdown_pct: float,
    *,
    max_drawdown_for_zero_risk_pct: float = _DEFAULT_MAX_DRAWDOWN_FOR_ZERO_RISK_PCT,
) -> float:
    """Scale down risk as current drawdown increases.

    Args:
        current_drawdown_pct: Current account drawdown from its equity
            peak, as a positive percentage.
        max_drawdown_for_zero_risk_pct: Drawdown level at which risk is
            scaled to zero (RISK_ENGINE.md: "Never increase risk after losses").

    Returns:
        A scaling factor in [0.0, 1.0]: 1.0 at zero (or negative) drawdown,
        linearly decreasing to 0.0 at `max_drawdown_for_zero_risk_pct` and beyond.
    """
    if current_drawdown_pct <= 0:
        return 1.0
    if current_drawdown_pct >= max_drawdown_for_zero_risk_pct:
        return 0.0
    return 1.0 - (current_drawdown_pct / max_drawdown_for_zero_risk_pct)


def compute_position_size(
    *,
    account_equity: float,
    risk_per_trade_pct: float,
    entry_price: float,
    stop_loss_price: float,
    current_drawdown_pct: float = 0.0,
    max_position_value: float | None = None,
) -> PositionSizeResult:
    """Compute a risk-based position size.

    Args:
        account_equity: Current account equity.
        risk_per_trade_pct: Baseline risk per trade, as a percentage of equity.
        entry_price: Planned entry price.
        stop_loss_price: Planned protective stop price (the invalidation level).
        current_drawdown_pct: Current account drawdown, used to scale down
            risk after losses.
        max_position_value: Optional cap on total position value
            (`entry_price * position_size_units`).

    Returns:
        A `PositionSizeResult`. Zero size if `entry_price == stop_loss_price`
        (no defined risk distance) or `account_equity <= 0` — never a
        fabricated size with no valid risk basis.

    Raises:
        ValueError: If `risk_per_trade_pct` is not positive.
    """
    if risk_per_trade_pct <= 0:
        raise ValueError("risk_per_trade_pct must be positive")

    stop_distance = abs(entry_price - stop_loss_price)
    if stop_distance == 0 or account_equity <= 0:
        return PositionSizeResult(
            position_size_units=0.0, risk_amount=0.0, effective_risk_pct=0.0
        )

    scaling_factor = compute_drawdown_scaling_factor(current_drawdown_pct)
    effective_risk_pct = risk_per_trade_pct * scaling_factor
    risk_amount = account_equity * effective_risk_pct / 100
    position_size_units = risk_amount / stop_distance

    if max_position_value is not None and entry_price > 0:
        position_size_units = min(position_size_units, max_position_value / entry_price)

    return PositionSizeResult(
        position_size_units=position_size_units,
        risk_amount=risk_amount,
        effective_risk_pct=effective_risk_pct,
    )
