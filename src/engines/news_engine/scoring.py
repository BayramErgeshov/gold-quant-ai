"""News importance and expected-volatility scoring.

Per NEWS_ENGINE.md ("Importance Score", "Volatility Estimation"): every
article receives an expected-volatility level and a combined importance
score. A deliberately explainable v1 mapping category -> impact, blended
with source reliability and entity richness — pending refinement once the
Historical Research Engine can measure each category's *actual* average
historical price reaction (HISTORICAL_RESEARCH_ENGINE.md).
"""

from __future__ import annotations

from typing import Literal

VolatilityLevel = Literal["low", "medium", "high"]

_HIGH_IMPACT_CATEGORIES = frozenset(
    {"central_bank", "employment", "gdp", "market_stress", "bank_failures", "geopolitics"}
)
_MEDIUM_IMPACT_CATEGORIES = frozenset({"inflation", "pmi", "etf_flows", "trade", "energy"})

_CATEGORY_WEIGHT_BY_VOLATILITY: dict[VolatilityLevel, float] = {
    "high": 1.0,
    "medium": 0.6,
    "low": 0.3,
}
_CATEGORY_SCORE_WEIGHT = 0.5
_SOURCE_RELIABILITY_WEIGHT = 0.3
_ENTITY_RICHNESS_WEIGHT = 0.2
_MAX_ENTITY_COUNT_FOR_FULL_WEIGHT = 5


def expected_volatility(category: str | None) -> VolatilityLevel:
    """Map a news category to an expected volatility level.

    Args:
        category: Classified event category, or None if unclassified.

    Returns:
        "high", "medium", or "low".
    """
    if category in _HIGH_IMPACT_CATEGORIES:
        return "high"
    if category in _MEDIUM_IMPACT_CATEGORIES:
        return "medium"
    return "low"


def compute_importance_score(
    *, category: str | None, source_reliability: float, entity_count: int
) -> float:
    """Compute an overall importance score for a news article.

    Args:
        category: Classified event category, or None.
        source_reliability: The provider's reliability score in [0.0, 1.0]
            (`src.core.data_collection.provider.DataProvider.reliability`).
        entity_count: Number of extracted entities across all categories.

    Returns:
        Importance score in [0.0, 1.0].
    """
    category_weight = _CATEGORY_WEIGHT_BY_VOLATILITY[expected_volatility(category)]
    entity_weight = min(1.0, entity_count / _MAX_ENTITY_COUNT_FOR_FULL_WEIGHT)

    return min(
        1.0,
        _CATEGORY_SCORE_WEIGHT * category_weight
        + _SOURCE_RELIABILITY_WEIGHT * source_reliability
        + _ENTITY_RICHNESS_WEIGHT * entity_weight,
    )
