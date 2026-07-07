"""Feature engineering for the Machine Learning Engine.

Per MACHINE_LEARNING_ENGINE.md "Feature Engineering": Momentum, Trend,
Volatility, Volume features computed from a rolling window of candles.
Reuses the Historical Research Engine's regime features
(`compute_regime_features`) rather than recomputing trend/volatility from
scratch, per CODING_STANDARDS.md ("Never duplicate functionality"). Time,
Session, Macro, Historical, Correlation, Pattern, AI Consensus and Risk
features (also listed in MACHINE_LEARNING_ENGINE.md) require inputs from
other departments' reports and are added incrementally as those
integrations are built, rather than approximated here.
"""

from __future__ import annotations

from src.engines.historical_engine.regime_detection import compute_features as _regime_features
from src.models.candle import Candle

_MIN_WINDOW_SIZE = 2

FEATURE_NAMES: tuple[str, ...] = (
    "momentum_pct",
    "trend_slope_pct",
    "volatility_pct",
    "range_width_pct",
    "volume_trend_pct",
)


def build_feature_vector(window: list[Candle]) -> dict[str, float]:
    """Compute a feature vector from a rolling window of candles.

    Args:
        window: Candles ordered by timestamp ascending, oldest first.

    Returns:
        A dict keyed by `FEATURE_NAMES`. All zero if `window` has fewer
        than two candles — never a fabricated non-zero estimate.
    """
    if len(window) < _MIN_WINDOW_SIZE:
        return dict.fromkeys(FEATURE_NAMES, 0.0)

    regime = _regime_features(window)
    first_close = window[0].close
    last_close = window[-1].close
    momentum_pct = ((last_close - first_close) / first_close * 100) if first_close else 0.0

    volumes = [candle.volume for candle in window if candle.volume is not None]
    volume_trend_pct = 0.0
    if len(volumes) >= _MIN_WINDOW_SIZE and volumes[0] != 0:
        volume_trend_pct = (volumes[-1] - volumes[0]) / volumes[0] * 100

    return {
        "momentum_pct": momentum_pct,
        "trend_slope_pct": regime.trend_slope_pct,
        "volatility_pct": regime.volatility_pct,
        "range_width_pct": regime.range_width_pct,
        "volume_trend_pct": volume_trend_pct,
    }
