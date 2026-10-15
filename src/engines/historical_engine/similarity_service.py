"""Historical similarity search orchestrator.

Builds rolling feature windows from stored candles, finds the historical
windows most similar to the most recent one, measures each match's
forward-return outcome, and persists the matches for future retrieval
(DATABASE.md `historical_similarities` table).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from datetime import datetime

from src.common.logging import get_logger
from src.engines.historical_engine.regime_detection import compute_features
from src.engines.historical_engine.similarity import (
    FeatureWeights,
    OutcomeStatistics,
    SimilarityMatch,
    compute_outcome_statistics,
    find_similar_windows,
)
from src.models.candle import Candle
from src.models.historical_similarity import HistoricalSimilarity
from src.repositories.candle_repository import CandleRepository
from src.repositories.historical_similarity_repository import HistoricalSimilarityRepository

logger = get_logger(__name__)

_MAX_CANDLES_CONSIDERED = 1_000_000


@dataclass(frozen=True, slots=True)
class SimilaritySearchResult:
    """Outcome of a full similarity search for the most recent window.

    Attributes:
        matches: Ranked historical analogues, most similar first.
        outcome_statistics: Aggregate forward-return statistics across
            matches that had enough subsequent data to measure an outcome.
    """

    matches: list[SimilarityMatch]
    outcome_statistics: OutcomeStatistics


def _rolling_windows(candles: list[Candle], window_size: int) -> list[tuple[int, list[Candle]]]:
    """Build overlapping windows of `window_size` candles.

    Args:
        candles: Candles ordered by timestamp ascending.
        window_size: Number of candles per window.

    Returns:
        `(end_index, window)` pairs, where `end_index` is the position in
        `candles` of the window's last candle.
    """
    if len(candles) < window_size:
        return []
    return [
        (end - 1, candles[end - window_size : end]) for end in range(window_size, len(candles) + 1)
    ]


class HistoricalSimilarityService:
    """Finds historical analogues for the most recent window and their outcomes."""

    def __init__(
        self,
        *,
        candle_repository: CandleRepository,
        similarity_repository: HistoricalSimilarityRepository,
    ) -> None:
        """Initialize the service (constructor injection).

        Args:
            candle_repository: Source of stored OHLCV candles.
            similarity_repository: Persists computed matches.
        """
        self._candles = candle_repository
        self._similarities = similarity_repository

    async def search(
        self,
        symbol_id: uuid.UUID,
        timeframe: str,
        *,
        window_size: int = 20,
        forward_bars: int = 10,
        top_n: int = 100,
        weights: FeatureWeights | None = None,
        as_of_timestamp: datetime | None = None,
        persist_matches: bool = True,
    ) -> SimilaritySearchResult:
        """Find historical analogues of the most recent window and their outcomes.

        Args:
            symbol_id: Symbol to search within.
            timeframe: One of `src.models.candle.TIMEFRAMES`.
            window_size: Number of candles per feature window
                (HISTORICAL_RESEARCH_ENGINE.md-style situational snapshot).
            forward_bars: Number of bars after each match to measure the
                outcome return over.
            top_n: Maximum number of matches to keep
                (HISTORICAL_RESEARCH_ENGINE.md: "Find Top 100").
            weights: Feature dimension weighting; defaults to equal weighting.
            as_of_timestamp: If set, only candles at or before this moment
                are considered at all -- both as the query window and as
                candidates. Required for Market Replay Mode, where the
                database already holds candles "from the future" relative
                to the replay's current position; without this bound the
                query window would silently become the DB's most recent
                candles instead of the replay's own current moment, and
                candidate matches could leak future outcomes. `None`
                (the default) preserves live behavior: "most recent
                window in the database."
            persist_matches: Whether to persist matches to
                `historical_similarities`. Market Replay Mode passes
                `False` -- a replay session's queries are not real
                trading decisions and must never mix into the same table
                real live scans write to.

        Returns:
            A `SimilaritySearchResult` with the ranked matches and
            aggregate outcome statistics. Empty if there is not yet enough
            historical data (fewer than two full windows) to compare
            against — never a fabricated result.
        """
        all_candles = await self._candles.list_range(
            symbol_id, timeframe, limit=_MAX_CANDLES_CONSIDERED
        )
        if as_of_timestamp is not None:
            all_candles = [candle for candle in all_candles if candle.timestamp <= as_of_timestamp]
        windows = _rolling_windows(all_candles, window_size)
        if len(windows) < 2:
            return SimilaritySearchResult(
                matches=[], outcome_statistics=compute_outcome_statistics([])
            )

        query_end_index, query_window = windows[-1]
        query_timestamp = all_candles[query_end_index].timestamp
        query_features = compute_features(query_window)

        candidate_entries = windows[:-1]
        candidates = [
            (all_candles[end_index].timestamp, compute_features(window))
            for end_index, window in candidate_entries
        ]
        matches = find_similar_windows(query_features, candidates, top_n=top_n, weights=weights)

        index_by_timestamp = {
            all_candles[end_index].timestamp: end_index for end_index, _ in candidate_entries
        }
        returns_pct: list[float] = []
        enriched_matches: list[SimilarityMatch] = []

        for match in matches:
            window_end_index = index_by_timestamp[match.timestamp]
            forward_index = window_end_index + forward_bars
            if forward_index >= len(all_candles):
                enriched_matches.append(match)
                continue

            entry_price = all_candles[window_end_index].close
            exit_price = all_candles[forward_index].close
            if entry_price == 0:
                enriched_matches.append(match)
                continue

            outcome_return_pct = (exit_price - entry_price) / entry_price * 100
            returns_pct.append(outcome_return_pct)
            # The path between entry and exit (exclusive of the entry bar
            # itself) -- how far price moved against a BUY/SELL held over
            # this same horizon, for the Trade Similarity Engine's
            # "Average drawdown"/"Average RR" (`summarize_matches_for_direction`).
            path = all_candles[window_end_index + 1 : forward_index + 1]
            if not path:
                enriched_matches.append(match)
                continue
            adverse_if_long_pct = max(
                0.0, (entry_price - min(candle.low for candle in path)) / entry_price * 100
            )
            adverse_if_short_pct = max(
                0.0, (max(candle.high for candle in path) - entry_price) / entry_price * 100
            )
            enriched_matches.append(
                replace(
                    match,
                    outcome_return_pct=outcome_return_pct,
                    adverse_if_long_pct=adverse_if_long_pct,
                    adverse_if_short_pct=adverse_if_short_pct,
                )
            )
            if not persist_matches:
                continue
            await self._similarities.add(
                HistoricalSimilarity(
                    symbol_id=symbol_id,
                    timeframe=timeframe,
                    query_timestamp=query_timestamp,
                    matched_timestamp=match.timestamp,
                    similarity_score=match.similarity_score,
                    outcome_return_pct=outcome_return_pct,
                )
            )

        logger.info(
            "historical_similarity_search_completed",
            symbol_id=str(symbol_id),
            timeframe=timeframe,
            matches=len(matches),
            with_outcome=len(returns_pct),
        )
        return SimilaritySearchResult(
            matches=enriched_matches, outcome_statistics=compute_outcome_statistics(returns_pct)
        )
