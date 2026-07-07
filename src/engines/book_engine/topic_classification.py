"""Keyword-based topic classification for book chunks.

Per BOOK_RAG.md "Topic Classification": every chunk is assigned to one or
more topics from a fixed taxonomy. This is a deliberately explainable v1 —
each topic has a curated keyword list and a chunk's score per topic is its
keyword hit count (via the shared `src.utils.keyword_classifier`).
BOOK_RAG.md's Machine Learning Department (a later roadmap phase) may
replace this with a trained classifier once validated topic-labeled
training data exists; until then, an explainable rule-based classifier is
more honest than an untrained "ML" placeholder.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.utils.keyword_classifier import primary_category, score_keywords

TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "market_structure": (
        "market structure", "higher high", "higher low", "lower high", "lower low",
        "break of structure", "change of character", "bos", "choch", "swing high", "swing low",
    ),
    "liquidity": (
        "liquidity", "liquidity pool", "liquidity sweep", "stop hunt", "equal highs",
        "equal lows", "buy side liquidity", "sell side liquidity",
    ),
    "order_flow": ("order flow", "delta", "footprint", "absorption", "aggression", "bid ask"),
    "smart_money": (
        "smart money", "order block", "breaker block", "mitigation block", "displacement",
        "imbalance", "institutional",
    ),
    "ict": (
        "kill zone", "optimal trade entry", "silver bullet", "power of three", "judas swing",
        "fair value gap",
    ),
    "wyckoff": (
        "wyckoff", "accumulation", "distribution", "spring", "upthrust", "composite operator",
        "sign of strength",
    ),
    "price_action": (
        "price action", "pin bar", "engulfing", "inside bar", "outside bar", "doji",
        "rejection candle",
    ),
    "risk": (
        "risk management", "position sizing", "stop loss", "risk reward", "drawdown",
        "capital preservation",
    ),
    "psychology": ("trading psychology", "discipline", "emotional", "fear", "greed", "patience"),
    "macro": (
        "macroeconomic", "interest rate", "inflation", "gdp", "central bank",
        "monetary policy", "employment",
    ),
    "central_banks": (
        "federal reserve", "fomc", "ecb", "bank of japan", "people's bank of china",
        "central bank",
    ),
    "gold": ("gold", "xauusd", "safe haven", "bullion"),
    "dollar": ("dollar index", "dxy", "us dollar", "greenback"),
    "volatility": (
        "volatility", "atr", "average true range", "implied volatility", "realized volatility",
    ),
    "execution": ("execution", "slippage", "spread", "order type", "market order", "limit order"),
    "portfolio_management": ("portfolio", "diversification", "asset allocation", "correlation"),
    "statistics": (
        "probability", "expectancy", "sharpe", "sortino", "standard deviation", "statistical",
    ),
    "machine_learning": (
        "machine learning", "neural network", "regression", "classification model",
        "feature importance",
    ),
    "artificial_intelligence": (
        "artificial intelligence", "deep learning", "large language model",
    ),
    "programming": ("python", "algorithm", "backtest engine", "programming language"),
    "backtesting": ("backtest", "walk forward", "monte carlo", "historical simulation"),
    "optimization": ("optimization", "parameter tuning", "overfitting", "curve fitting"),
    "behavioral_finance": (
        "behavioral finance", "cognitive bias", "loss aversion", "herd behavior",
    ),
}

@dataclass(frozen=True, slots=True)
class TopicScore:
    """A single topic's keyword-match score for a chunk of text."""

    topic: str
    score: float


def classify_topics(text: str, *, max_topics: int = 3) -> list[TopicScore]:
    """Score and rank topics for a chunk of text.

    Args:
        text: Chunk text to classify.
        max_topics: Maximum number of topics to return.

    Returns:
        Up to `max_topics` `TopicScore`, sorted by score descending,
        excluding topics with zero keyword hits. Empty if nothing matches.
    """
    return [
        TopicScore(topic=keyword_score.category, score=keyword_score.score)
        for keyword_score in score_keywords(text, TOPIC_KEYWORDS, max_categories=max_topics)
    ]


def primary_topic(text: str) -> str | None:
    """Return only the single highest-scoring topic for a chunk of text.

    Args:
        text: Chunk text to classify.

    Returns:
        The highest-scoring topic name, or None if no keyword matched.
    """
    return primary_category(text, TOPIC_KEYWORDS)
