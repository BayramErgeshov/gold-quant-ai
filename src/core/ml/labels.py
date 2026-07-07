"""Label generation for the Machine Learning Engine.

Per MACHINE_LEARNING_ENGINE.md "Label Generation": every training sample
is assigned a direction/strength label from its forward return, using
fixed, documented thresholds — an explainable rule, not a fabricated
"ground truth". Volatility/trend/range/reversal/continuation labels are
better sourced directly from the Historical Research Engine's regime
classifier (`src.engines.historical_engine.regime_detection`) rather than
duplicated here.
"""

from __future__ import annotations

from dataclasses import dataclass

LABELS: tuple[str, ...] = (
    "strong_bearish",
    "bearish",
    "neutral",
    "bullish",
    "strong_bullish",
)


@dataclass(frozen=True, slots=True)
class LabelThresholds:
    """Forward-return %-thresholds separating each label.

    Attributes:
        neutral_band_pct: Forward returns within +/- this % are "neutral".
        strong_move_pct: Forward returns beyond +/- this % are "strong_*".
    """

    neutral_band_pct: float = 0.1
    strong_move_pct: float = 1.0


def compute_label(
    forward_return_pct: float, thresholds: LabelThresholds | None = None
) -> str:
    """Classify a forward return into a directional label.

    Args:
        forward_return_pct: Percentage price change from entry to a fixed
            number of bars later (positive = price rose).
        thresholds: Decision boundaries; defaults to `LabelThresholds()`.

    Returns:
        One of `LABELS`.
    """
    resolved = thresholds or LabelThresholds()

    if abs(forward_return_pct) <= resolved.neutral_band_pct:
        return "neutral"
    if forward_return_pct >= resolved.strong_move_pct:
        return "strong_bullish"
    if forward_return_pct <= -resolved.strong_move_pct:
        return "strong_bearish"
    return "bullish" if forward_return_pct > 0 else "bearish"
