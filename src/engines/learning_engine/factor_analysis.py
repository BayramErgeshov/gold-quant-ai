"""Trade outcome factor analysis for the Self Learning Engine.

Per SELF_LEARNING_ENGINE.md "Error Analysis" / "Win Analysis": for every
closed trade, determine which measurable factors contributed to its
outcome. Each check is a concrete, reproducible comparison against the
trade's own recorded decision context — never a fabricated narrative
explanation.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.models.trade import Trade

_STOP_TO_VOLATILITY_RATIO_THRESHOLD = 0.5


@dataclass(frozen=True, slots=True)
class TradeContext:
    """Recorded decision context for a closed trade, beyond the `Trade` row itself.

    Attributes:
        confidence_pct: The Chief AI decision confidence at entry.
        confidence_threshold: The threshold that was required to execute.
        historical_edge_pct: The historical edge measured for the setup.
        min_historical_edge_pct: The minimum edge that was required.
        market_regime: Classified regime at entry, if known.
        news_imminent_at_entry: Whether high-impact news was imminent at entry.
        expected_volatility_pct: Expected volatility (e.g. ATR-based), if known.
    """

    confidence_pct: float
    confidence_threshold: float
    historical_edge_pct: float
    min_historical_edge_pct: float
    market_regime: str | None
    news_imminent_at_entry: bool
    expected_volatility_pct: float | None


@dataclass(frozen=True, slots=True)
class TradeFactor:
    """One measurable factor identified for a closed trade's outcome."""

    name: str
    detail: str


def _stop_was_too_close(trade: Trade, context: TradeContext) -> bool:
    if (
        context.expected_volatility_pct is None
        or trade.entry_price is None
        or trade.entry_price == 0
    ):
        return False
    stop_distance_pct = abs(trade.entry_price - trade.stop_loss) / trade.entry_price * 100
    return stop_distance_pct < context.expected_volatility_pct * _STOP_TO_VOLATILITY_RATIO_THRESHOLD


def analyze_losing_trade(trade: Trade, context: TradeContext) -> list[TradeFactor]:
    """Apply SELF_LEARNING_ENGINE.md "Error Analysis" checks to a losing trade.

    Args:
        trade: The closed, losing `Trade`.
        context: Recorded decision context at entry.

    Returns:
        Every measurable mistake factor identified. Empty if none of the
        checkable conditions applied — never a fabricated cause.
    """
    factors: list[TradeFactor] = []

    if context.confidence_pct < context.confidence_threshold:
        factors.append(
            TradeFactor(
                name="confidence_below_threshold",
                detail=(
                    f"Entry confidence {context.confidence_pct:.1f}% was below the "
                    f"required threshold {context.confidence_threshold:.1f}%."
                ),
            )
        )
    if context.historical_edge_pct < context.min_historical_edge_pct:
        factors.append(
            TradeFactor(
                name="weak_historical_edge",
                detail=(
                    f"Historical edge {context.historical_edge_pct:.2f}% was below the "
                    f"required minimum {context.min_historical_edge_pct:.2f}%."
                ),
            )
        )
    if context.market_regime is None:
        factors.append(
            TradeFactor(
                name="unknown_market_regime", detail="Market regime was unclassified at entry."
            )
        )
    if context.news_imminent_at_entry:
        factors.append(
            TradeFactor(
                name="news_ignored", detail="High-impact news was imminent at entry."
            )
        )
    if _stop_was_too_close(trade, context):
        factors.append(
            TradeFactor(
                name="stop_too_close",
                detail=(
                    f"Stop distance was small relative to expected volatility "
                    f"({context.expected_volatility_pct:.2f}%)."
                ),
            )
        )
    return factors


def analyze_winning_trade(trade: Trade, context: TradeContext) -> list[TradeFactor]:
    """Apply SELF_LEARNING_ENGINE.md "Win Analysis" checks to a winning trade.

    Args:
        trade: The closed, winning `Trade`. Unused directly today (kept for
            symmetry with `analyze_losing_trade` and future MFE/MAE-based checks).
        context: Recorded decision context at entry.

    Returns:
        Every measurable success factor identified. Empty if none of the
        checkable conditions applied.
    """
    factors: list[TradeFactor] = []

    if context.confidence_pct >= context.confidence_threshold:
        factors.append(
            TradeFactor(
                name="confidence_above_threshold",
                detail=(
                    f"Entry confidence {context.confidence_pct:.1f}% met the required "
                    f"threshold {context.confidence_threshold:.1f}%."
                ),
            )
        )
    if context.historical_edge_pct >= context.min_historical_edge_pct:
        factors.append(
            TradeFactor(
                name="strong_historical_edge",
                detail=(
                    f"Historical edge {context.historical_edge_pct:.2f}% met the required "
                    f"minimum {context.min_historical_edge_pct:.2f}%."
                ),
            )
        )
    if context.market_regime is not None:
        factors.append(
            TradeFactor(
                name="known_market_regime",
                detail=f"Market regime was classified as {context.market_regime!r} at entry.",
            )
        )
    return factors
