"""Rule-based market regime classification.

Per HISTORICAL_RESEARCH_ENGINE.md ("Every historical candle belongs to
Bull Trend, Bear Trend, Range... Expansion, Compression") and
MARKET_ANALYSIS_ENGINE.md ("Market Regime... Confidence, Historical
Validation"). A deliberately explainable v1: trend direction from linear
regression slope, volatility from the stddev of log returns, range width
from the high/low spread — all measurable, reproducible criteria.
MACHINE_LEARNING_ENGINE.md's Machine Learning Engine (a later roadmap
phase) may augment this with a trained classifier, but "never overrides
the Research Departments; it provides additional evidence" — so an
explainable rule-based classifier remains the baseline.

Accumulation/Distribution classification requires Wyckoff-specific
structure (springs, upthrusts, composite operator behavior) that belongs
to the dedicated Wyckoff Engine in TECHNICAL_ANALYSIS.md (Phase 6); this
module classifies the six regimes measurable from price/volatility alone.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.models.candle import Candle
from src.utils.statistics import linear_regression_slope_pct, log_return_stddev_pct

_MIN_WINDOW_SIZE = 2


@dataclass(frozen=True, slots=True)
class RegimeThresholds:
    """Configurable decision boundaries for regime classification.

    Attributes:
        trend_slope_pct: Minimum %-per-bar linear regression slope
            (normalized by average price) to call the window trending.
        high_volatility_pct: Stddev of bar-over-bar log returns (%) above
            which the window is classified "high_volatility".
        low_volatility_pct: Stddev of bar-over-bar log returns (%) below
            which the window is classified "low_volatility".
        range_width_pct: Maximum (high-low)/average_price (%) for a
            non-trending, non-volatile window to be classified "range".
    """

    trend_slope_pct: float = 0.15
    high_volatility_pct: float = 1.2
    low_volatility_pct: float = 0.15
    range_width_pct: float = 2.0


@dataclass(frozen=True, slots=True)
class RegimeFeatures:
    """Measurable inputs to regime classification, kept for explainability."""

    trend_slope_pct: float
    volatility_pct: float
    range_width_pct: float


@dataclass(frozen=True, slots=True)
class RegimeClassification:
    """The classified regime for a window, with its confidence and inputs."""

    regime: str
    confidence: float
    features: RegimeFeatures


def compute_features(window: list[Candle]) -> RegimeFeatures:
    """Compute trend/volatility/range features for a window of candles.

    Args:
        window: At least 2 candles, ordered by timestamp ascending.

    Returns:
        The computed `RegimeFeatures`.

    Raises:
        ValueError: If `window` has fewer than 2 candles.
    """
    if len(window) < _MIN_WINDOW_SIZE:
        raise ValueError("compute_features requires at least 2 candles")

    closes = [candle.close for candle in window]
    average_price = sum(closes) / len(closes)
    range_width_pct = (
        (max(candle.high for candle in window) - min(candle.low for candle in window))
        / average_price
        * 100
        if average_price
        else 0.0
    )

    return RegimeFeatures(
        trend_slope_pct=linear_regression_slope_pct(closes),
        volatility_pct=log_return_stddev_pct(closes),
        range_width_pct=range_width_pct,
    )


def classify_regime(
    window: list[Candle], *, thresholds: RegimeThresholds | None = None
) -> RegimeClassification:
    """Classify the market regime for a window of candles.

    Args:
        window: At least 2 candles, ordered by timestamp ascending.
        thresholds: Decision boundaries; defaults to `RegimeThresholds()`.

    Returns:
        A `RegimeClassification` with the chosen regime, a confidence
        score in [0.0, 1.0], and the underlying measured features.
    """
    resolved_thresholds = thresholds or RegimeThresholds()
    features = compute_features(window)

    # Trend is checked first: a smooth, low-noise trend is still a trend,
    # not merely "low_volatility" — direction takes priority over how
    # noisy the path to get there was. Range is checked next (a tight,
    # non-trending band), leaving volatility extremes to classify the
    # remaining non-trending, non-tight-range windows.
    if features.trend_slope_pct >= resolved_thresholds.trend_slope_pct:
        regime = "bull_trend"
        confidence = min(1.0, features.trend_slope_pct / (resolved_thresholds.trend_slope_pct * 2))
    elif features.trend_slope_pct <= -resolved_thresholds.trend_slope_pct:
        regime = "bear_trend"
        confidence = min(
            1.0, abs(features.trend_slope_pct) / (resolved_thresholds.trend_slope_pct * 2)
        )
    elif features.range_width_pct <= resolved_thresholds.range_width_pct:
        regime = "range"
        confidence = min(1.0, 1.0 - features.range_width_pct / resolved_thresholds.range_width_pct)
    elif features.volatility_pct >= resolved_thresholds.high_volatility_pct:
        regime = "high_volatility"
        confidence = min(
            1.0, features.volatility_pct / (resolved_thresholds.high_volatility_pct * 2)
        )
    elif features.volatility_pct <= resolved_thresholds.low_volatility_pct:
        regime = "low_volatility"
        confidence = (
            1.0
            if resolved_thresholds.low_volatility_pct == 0
            else min(1.0, 1.0 - features.volatility_pct / resolved_thresholds.low_volatility_pct)
        )
    else:
        regime = "transition"
        confidence = 0.5

    return RegimeClassification(regime=regime, confidence=max(0.0, confidence), features=features)
