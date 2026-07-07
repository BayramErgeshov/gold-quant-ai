"""Historical analogue similarity search.

Per HISTORICAL_RESEARCH_ENGINE.md: "For every current market situation...
Search entire database... Find Top 100 Most Similar Situations...
Calculate Similarity Score... For every similar situation calculate
Average Move... Win Rate... Continuation Probability."

Scope note: similarity here is computed from measurable price/volatility
features (`RegimeFeatures` from `regime_detection.py`) — the trend,
volatility and range-width shape of a window. Liquidity, macro and news
similarity dimensions listed in HISTORICAL_RESEARCH_ENGINE.md require
those engines (Phases 7-8) and are added as additional feature dimensions
once available, without changing this module's interface.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from src.engines.historical_engine.regime_detection import RegimeFeatures


@dataclass(frozen=True, slots=True)
class FeatureWeights:
    """Relative importance of each feature dimension in similarity scoring."""

    trend_weight: float = 1.0
    volatility_weight: float = 1.0
    range_weight: float = 1.0


@dataclass(frozen=True, slots=True)
class SimilarityMatch:
    """A single historical window judged similar to the query window.

    Attributes:
        timestamp: The historical window's reference timestamp (typically
            its last candle's timestamp).
        similarity_score: Similarity in (0.0, 1.0]; 1.0 means identical
            feature vectors.
        features: The historical window's measured features.
    """

    timestamp: datetime
    similarity_score: float
    features: RegimeFeatures


@dataclass(frozen=True, slots=True)
class OutcomeStatistics:
    """Aggregate statistics over matched analogues' subsequent price returns.

    Attributes:
        sample_size: Number of matches with a known outcome return.
        win_rate: Fraction of matches with a positive return, in [0.0, 1.0].
        average_return_pct: Mean forward return, in percent.
        median_return_pct: Median forward return, in percent.
        max_return_pct: Best-case forward return observed, in percent.
        min_return_pct: Worst-case forward return observed, in percent.
    """

    sample_size: int
    win_rate: float
    average_return_pct: float
    median_return_pct: float
    max_return_pct: float
    min_return_pct: float


def compute_similarity(
    query: RegimeFeatures, candidate: RegimeFeatures, *, weights: FeatureWeights | None = None
) -> float:
    """Score how similar a candidate window is to the query window.

    Uses a weighted Euclidean distance across (trend, volatility, range)
    features, transformed to a bounded (0.0, 1.0] similarity score via
    `1 / (1 + distance)` — 0 distance maps to 1.0, larger distances decay
    asymptotically toward 0.

    Args:
        query: Features of the current/reference window.
        candidate: Features of a historical window being compared.
        weights: Relative importance per dimension; defaults to equal
            weighting.

    Returns:
        A similarity score in (0.0, 1.0].
    """
    resolved_weights = weights or FeatureWeights()
    distance = math.sqrt(
        resolved_weights.trend_weight * (query.trend_slope_pct - candidate.trend_slope_pct) ** 2
        + resolved_weights.volatility_weight
        * (query.volatility_pct - candidate.volatility_pct) ** 2
        + resolved_weights.range_weight * (query.range_width_pct - candidate.range_width_pct) ** 2
    )
    return 1.0 / (1.0 + distance)


def find_similar_windows(
    query: RegimeFeatures,
    candidates: Sequence[tuple[datetime, RegimeFeatures]],
    *,
    top_n: int = 100,
    weights: FeatureWeights | None = None,
) -> list[SimilarityMatch]:
    """Rank candidate historical windows by similarity to the query window.

    Args:
        query: Features of the current/reference window.
        candidates: `(timestamp, features)` pairs for every historical
            window to consider.
        top_n: Maximum number of matches to return
            (HISTORICAL_RESEARCH_ENGINE.md: "Find Top 100").
        weights: Relative importance per dimension; defaults to equal
            weighting.

    Returns:
        Up to `top_n` `SimilarityMatch`, most similar first.
    """
    scored = [
        SimilarityMatch(
            timestamp=timestamp,
            similarity_score=compute_similarity(query, features, weights=weights),
            features=features,
        )
        for timestamp, features in candidates
    ]
    scored.sort(key=lambda match: match.similarity_score, reverse=True)
    return scored[:top_n]


def compute_outcome_statistics(returns_pct: list[float]) -> OutcomeStatistics:
    """Aggregate forward-return statistics across matched analogues.

    Args:
        returns_pct: Forward price return (%) observed after each matched
            historical window.

    Returns:
        An `OutcomeStatistics` summarizing the distribution. All fields
        are 0.0 if `returns_pct` is empty.
    """
    if not returns_pct:
        return OutcomeStatistics(
            sample_size=0,
            win_rate=0.0,
            average_return_pct=0.0,
            median_return_pct=0.0,
            max_return_pct=0.0,
            min_return_pct=0.0,
        )

    wins = sum(1 for value in returns_pct if value > 0)
    return OutcomeStatistics(
        sample_size=len(returns_pct),
        win_rate=wins / len(returns_pct),
        average_return_pct=statistics.mean(returns_pct),
        median_return_pct=statistics.median(returns_pct),
        max_return_pct=max(returns_pct),
        min_return_pct=min(returns_pct),
    )
