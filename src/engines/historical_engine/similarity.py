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
from typing import Literal

from src.engines.historical_engine.regime_detection import RegimeFeatures
from src.engines.historical_engine.validation import TIMEFRAME_INTERVALS


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
        outcome_return_pct: Forward price return (%) observed after this
            match, over `HistoricalSimilarityService.search()`'s own
            `forward_bars` horizon. None until
            `HistoricalSimilarityService.search()` has measured it (not
            enough subsequent history yet).
        adverse_if_long_pct: How far price fell below this match's entry
            price at its worst point before the outcome was measured, as
            a positive percentage -- the drawdown a BUY would have sat
            through. None until measured.
        adverse_if_short_pct: How far price rose above this match's entry
            price at its worst point before the outcome was measured, as
            a positive percentage -- the drawdown a SELL would have sat
            through. None until measured.
    """

    timestamp: datetime
    similarity_score: float
    features: RegimeFeatures
    outcome_return_pct: float | None = None
    adverse_if_long_pct: float | None = None
    adverse_if_short_pct: float | None = None


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


@dataclass(frozen=True, slots=True)
class SimilarityDisplayStats:
    """Trade Similarity Engine's "before every trade" summary, for one direction.

    Per the "Trade Similarity Engine" production requirement: "Before
    opening every trade search the historical database. Find the most
    similar historical situations... Return: How many similar situations
    were found. How many became profitable. How many failed. Average RR.
    Average holding time. Average drawdown."

    Attributes:
        found_count: Matches with a measured outcome (enough subsequent
            history existed to measure one).
        profitable_count: Of those, how many moved in `direction`'s favor.
        failed_count: Of those, how many moved against `direction` (or
            were exactly flat).
        win_rate_pct: `profitable_count / found_count * 100`, or None if
            `found_count` is 0 -- never a fabricated rate from zero samples.
        average_rr: Mean of (favorable move / adverse excursion against
            `direction`) across matches with a nonzero adverse excursion
            -- how much reward historical analogues offered relative to
            how far price moved against `direction` along the way. This
            describes THOSE historical situations, not a promise about
            this trade's own risk/reward. None if no match had a
            measurable, nonzero adverse excursion.
        average_holding_time_minutes: The fixed forward-bar horizon every
            match's outcome was measured over, in minutes -- a parameter
            of the search (identical for every match), not a per-match
            measured duration.
        average_drawdown_pct: Mean adverse excursion against `direction`
            across matches with one measured. None if `found_count` is 0.
    """

    found_count: int
    profitable_count: int
    failed_count: int
    win_rate_pct: float | None
    average_rr: float | None
    average_holding_time_minutes: float
    average_drawdown_pct: float | None


def summarize_matches_for_direction(
    matches: list[SimilarityMatch],
    direction: Literal["buy", "sell"],
    *,
    forward_bars: int,
    timeframe: str,
) -> SimilarityDisplayStats:
    """Summarize matched historical analogues relative to one trade direction.

    `HistoricalSimilarityService.search()` finds analogues before a
    direction is even chosen (its outcome statistics feed Chief AI's own
    directional read); this re-evaluates those same matches once a
    direction has actually been decided, so "profitable"/"failed" means
    "would have favored THIS trade," not just "price went up."

    Args:
        matches: `SimilaritySearchResult.matches` from `search()`, already
            carrying each match's measured `outcome_return_pct`/
            `adverse_if_long_pct`/`adverse_if_short_pct` (matches without
            a measured outcome are excluded).
        direction: The trade direction about to be taken.
        forward_bars: The same `forward_bars` passed to `search()`, so
            `average_holding_time_minutes` reflects the actual horizon
            the outcomes were measured over.
        timeframe: One of `src.models.candle.TIMEFRAMES`.

    Returns:
        A `SimilarityDisplayStats` for `direction`. `found_count` is 0
        (every other field None, apart from `average_holding_time_minutes`)
        if no match has a measured outcome yet.
    """
    bar_minutes = (
        TIMEFRAME_INTERVALS[timeframe].total_seconds() / 60
        if timeframe in TIMEFRAME_INTERVALS
        else 0.0
    )
    average_holding_time_minutes = forward_bars * bar_minutes

    measured = [m for m in matches if m.outcome_return_pct is not None]
    if not measured:
        return SimilarityDisplayStats(
            found_count=0,
            profitable_count=0,
            failed_count=0,
            win_rate_pct=None,
            average_rr=None,
            average_holding_time_minutes=average_holding_time_minutes,
            average_drawdown_pct=None,
        )

    is_long = direction == "buy"
    profitable_count = 0
    adverse_excursions: list[float] = []
    rr_samples: list[float] = []
    for match in measured:
        assert match.outcome_return_pct is not None
        favorable_move = match.outcome_return_pct if is_long else -match.outcome_return_pct
        if favorable_move > 0:
            profitable_count += 1
        adverse = match.adverse_if_long_pct if is_long else match.adverse_if_short_pct
        if adverse is not None:
            adverse_excursions.append(adverse)
            if adverse > 0:
                rr_samples.append(abs(favorable_move) / adverse)

    found_count = len(measured)

    return SimilarityDisplayStats(
        found_count=found_count,
        profitable_count=profitable_count,
        failed_count=found_count - profitable_count,
        win_rate_pct=profitable_count / found_count * 100,
        average_rr=statistics.mean(rr_samples) if rr_samples else None,
        average_holding_time_minutes=average_holding_time_minutes,
        average_drawdown_pct=statistics.mean(adverse_excursions) if adverse_excursions else None,
    )
