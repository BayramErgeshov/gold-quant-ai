"""News category classification (NEWS_ENGINE.md: "Event Types").

Keyword-based classification against a subset of NEWS_ENGINE.md's event
taxonomy, using the shared `src.utils.keyword_classifier` (the same
pattern as the Book Engine's topic classifier) — a deliberately
explainable v1, pending a trained classifier from the Machine Learning
Engine (a later roadmap phase).
"""

from __future__ import annotations

from src.utils.keyword_classifier import primary_category

NEWS_CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "central_bank": (
        "federal reserve",
        "fomc",
        "rate decision",
        "central bank",
        "interest rate decision",
        "monetary policy",
    ),
    "inflation": ("inflation", "cpi", "consumer price index", "ppi", "pce"),
    "employment": (
        "nonfarm payrolls",
        "non-farm payrolls",
        "unemployment",
        "jobless claims",
        "employment report",
    ),
    "gdp": ("gdp", "gross domestic product", "economic growth"),
    "pmi": ("pmi", "purchasing managers", "ism manufacturing", "ism services"),
    "geopolitics": ("war", "conflict", "sanctions", "geopolitical", "invasion", "ceasefire"),
    "gold_supply": ("gold mine", "gold production", "gold reserves", "gold supply"),
    "etf_flows": ("gold etf", "etf inflow", "etf outflow", "spdr gold"),
    "bank_failures": ("bank failure", "bank collapse", "banking crisis"),
    "market_stress": ("flash crash", "market crash", "liquidity crisis", "circuit breaker"),
    "trade": ("tariff", "trade agreement", "trade war", "trade deal"),
    "energy": ("oil price", "opec", "energy crisis"),
}


def classify_news_category(text: str) -> str | None:
    """Classify a news article into an event category.

    Args:
        text: Article title (and summary, if available), concatenated.

    Returns:
        The highest-scoring category name, or None if nothing matched.
    """
    return primary_category(text, NEWS_CATEGORY_KEYWORDS)
