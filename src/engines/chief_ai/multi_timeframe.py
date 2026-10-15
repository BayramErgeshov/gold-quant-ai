"""Multi-timeframe confirmation helpers, shared across all three engines.

Per the "Complete Multi-Timeframe Analysis" production requirement: every
strategy must independently analyze every timeframe relevant to its own
role (primary/confirmation/entry), not just its own primary decision
timeframe. Reuses `classify_regime` (already timeframe-agnostic --
`src.engines.historical_engine.regime_detection`) rather than inventing
new per-timeframe logic; this module only generalizes the confirmation/
discount bookkeeping already proven for Scalping/Swing's own existing
single-timeframe counter-trend discount (`_COUNTER_TREND_CONFIDENCE_DISCOUNT`
in each engine's `service.py`) to an arbitrary number of confirmation
layers, so multiple higher/lower timeframes can each independently
confirm or discount a candidate direction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from src.engines.historical_engine.regime_detection import classify_regime
from src.models.candle import Candle

_TREND_REGIMES: frozenset[str] = frozenset({"bull_trend", "bear_trend"})
_MIN_CANDLES_FOR_REGIME = 20
_DEFAULT_DISCOUNT_PER_DISAGREEMENT = 0.5


@dataclass(frozen=True, slots=True)
class TimeframeConfirmation:
    """One additional timeframe's own regime read against a candidate direction.

    Attributes:
        timeframe: The timeframe checked, e.g. "H4".
        regime: The classified regime, if enough candles were available.
        agrees: Whether `regime` aligns with the candidate direction. None
            when `regime` is None (not enough history) or the timeframe
            is not in a trend regime (range/etc.) -- a genuinely neutral
            read, never a fabricated agreement or disagreement.
    """

    timeframe: str
    regime: str | None
    agrees: bool | None


def confirm_timeframe(
    timeframe: str, candles: list[Candle], direction: Literal["buy", "sell"]
) -> TimeframeConfirmation:
    """Check one additional timeframe's own regime against a candidate direction.

    Args:
        timeframe: The timeframe being checked, for labeling only --
            `candles` must already belong to this timeframe.
        candles: That timeframe's own recent candles, ordered ascending.
        direction: The candidate trade direction being confirmed.

    Returns:
        A `TimeframeConfirmation`. `agrees` is None (neither True nor
        False) whenever there is too little history or the timeframe
        isn't trending -- an honest "no evidence either way," never a
        fabricated confirmation.
    """
    if len(candles) < _MIN_CANDLES_FOR_REGIME:
        return TimeframeConfirmation(timeframe=timeframe, regime=None, agrees=None)
    regime = classify_regime(candles).regime
    if regime not in _TREND_REGIMES:
        return TimeframeConfirmation(timeframe=timeframe, regime=regime, agrees=None)
    is_bull = regime == "bull_trend"
    agrees = is_bull == (direction == "buy")
    return TimeframeConfirmation(timeframe=timeframe, regime=regime, agrees=agrees)


@dataclass(frozen=True, slots=True)
class MultiTimeframeResult:
    """The combined result of checking every additional confirmation timeframe.

    Attributes:
        confirmations: Every timeframe checked, in the order given.
        confidence_multiplier: Product of a per-disagreement discount --
            1.0 when every checked timeframe agrees or had no opinion,
            below 1.0 for each timeframe that actively disagreed.
        reasons: Human-readable tags for the confirming/disagreeing timeframes.
    """

    confirmations: list[TimeframeConfirmation] = field(default_factory=list)
    confidence_multiplier: float = 1.0
    reasons: list[str] = field(default_factory=list)


def combine_timeframe_confirmations(
    confirmations: list[TimeframeConfirmation],
    *,
    discount_per_disagreement: float = _DEFAULT_DISCOUNT_PER_DISAGREEMENT,
) -> MultiTimeframeResult:
    """Fold every additional timeframe's confirmation into one discount + reasons.

    Args:
        confirmations: Every `TimeframeConfirmation` checked this cycle.
        discount_per_disagreement: Multiplicative confidence penalty
            applied for each timeframe that actively disagreed -- mirrors
            each engine's own existing single-timeframe counter-trend
            discount, applied once per disagreeing timeframe rather than
            only once total.

    Returns:
        A `MultiTimeframeResult` with the combined multiplier and reasons.
    """
    multiplier = 1.0
    reasons: list[str] = []
    for confirmation in confirmations:
        if confirmation.agrees is True:
            reasons.append(f"{confirmation.timeframe}_confirms:{confirmation.regime}")
        elif confirmation.agrees is False:
            multiplier *= discount_per_disagreement
            reasons.append(f"{confirmation.timeframe}_counter_trend:{confirmation.regime}")
    return MultiTimeframeResult(
        confirmations=confirmations, confidence_multiplier=multiplier, reasons=reasons
    )
