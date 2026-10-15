"""Historical market reaction measurement for news categories.

Completes the cross-engine join `src.engines.news_engine.linking`'s own
docstring anticipates: `find_related_articles` finds prior articles
sharing a category, but "measuring each linked article's *actual*
average/median/worst/best-case market reaction... is deferred until that
cross-engine integration is built -- never approximated here." This
module is that integration: for each linked article, it looks up the
already-stored candle at (or just after) `NewsArticle.published_at` and
one `forward_bars` later, and computes the realized forward return --
genuine historical data, never a fabricated "expected reaction."
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from src.models.news_article import NewsArticle
from src.repositories.candle_repository import CandleRepository
from src.utils.statistics import forward_return_pct

# Below this many measured reactions, "insufficient data" is the only
# honest answer -- the same floor `src.engines.book_engine.claim_validation`
# uses for the identical reason (a provisional, CLT-backed minimum, not a
# precisely tuned number).
_MIN_SAMPLE_SIZE = 5


@dataclass(frozen=True, slots=True)
class HistoricalReactionEstimate:
    """A news category's measured historical price reaction.

    Attributes:
        category: The event category measured.
        sample_size: Number of past articles with enough subsequent
            candle history to measure.
        average_return_pct: Mean forward return across the sample, in
            percent (signed -- positive means price rose).
        best_case_return_pct: The single most favorable (highest) return
            observed.
        worst_case_return_pct: The single least favorable (lowest) return
            observed -- the "alternative scenario" if this reaction does
            not repeat.
    """

    category: str
    sample_size: int
    average_return_pct: float
    best_case_return_pct: float
    worst_case_return_pct: float


async def measure_historical_reaction(
    *,
    category: str,
    articles: list[NewsArticle],
    candle_repository: CandleRepository,
    symbol_id: uuid.UUID,
    timeframe: str,
    forward_bars: int,
) -> HistoricalReactionEstimate | None:
    """Measure a news category's realized historical price reaction.

    Args:
        category: The event category being measured (e.g. from
            `src.engines.news_engine.linking.find_related_articles`'s
            input article's own `category`).
        articles: Prior articles in this category (typically
            `find_related_articles`'s own output).
        candle_repository: Source of stored candles.
        symbol_id: The symbol to measure reaction on (e.g. XAUUSD).
        timeframe: Candle timeframe to measure on.
        forward_bars: How many bars after each article's `published_at`
            to measure the return over.

    Returns:
        The `HistoricalReactionEstimate`, or None if fewer than
        `_MIN_SAMPLE_SIZE` articles had enough subsequent candle history
        to measure -- never a fabricated estimate from too little data.
    """
    returns: list[float] = []
    for article in articles:
        candles = await candle_repository.list_range(
            symbol_id, timeframe, start=article.published_at, limit=forward_bars + 1
        )
        if len(candles) < forward_bars + 1:
            continue
        returns.append(forward_return_pct(candles[0].close, candles[forward_bars].close))

    if len(returns) < _MIN_SAMPLE_SIZE:
        return None

    return HistoricalReactionEstimate(
        category=category,
        sample_size=len(returns),
        average_return_pct=sum(returns) / len(returns),
        best_case_return_pct=max(returns),
        worst_case_return_pct=min(returns),
    )
