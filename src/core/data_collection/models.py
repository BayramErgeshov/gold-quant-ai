"""Shared data types for the Data Collection Engine.

Per DATA_COLLECTION_ENGINE.md: "Every dataset receives a quality score...
a timestamp... a source... a confidence score." These types are the
universal envelope every provider result is wrapped in before it reaches
any research department.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class ProviderTier(StrEnum):
    """Source tier, per DATA_COLLECTION_ENGINE.md fallback chain ordering."""

    TIER_1 = "tier_1"
    TIER_2 = "tier_2"
    TIER_3 = "tier_3"


class SourceCategory(StrEnum):
    """High-level data category, per DATA_COLLECTION_ENGINE.md "Data Sources"."""

    MARKET_DATA = "market_data"
    ECONOMIC_DATA = "economic_data"
    NEWS = "news"
    RESEARCH = "research"
    ALTERNATIVE_DATA = "alternative_data"


class DataQualityGrade(StrEnum):
    """Institutional data quality grade, per DATA_QUALITY_STANDARD.md."""

    AAA = "AAA"
    AA = "AA"
    A = "A"
    BBB = "BBB"
    BB = "BB"
    B = "B"
    C = "C"


@dataclass(frozen=True, slots=True)
class DataQualityScore:
    """Multi-dimensional data quality assessment (DATA_QUALITY_STANDARD.md).

    Every dimension is a 0.0-1.0 score; `overall` is their weighted average
    and `grade` is the corresponding institutional grade.
    """

    freshness: float
    completeness: float
    reliability: float
    consistency: float
    accuracy: float
    overall: float
    grade: DataQualityGrade


@dataclass(frozen=True, slots=True)
class CollectionMetadata:
    """Provenance and quality metadata attached to every collected dataset.

    Attributes:
        source: Name of the provider that produced the data.
        category: Data category the provider belongs to.
        tier: Provider tier (tier_1 = most authoritative).
        collected_at: UTC timestamp of collection.
        quality: Computed data quality score.
        is_cached: True if this result was served from cache rather than
            fetched live (DATA_COLLECTION_ENGINE.md fallback chain).
    """

    source: str
    category: SourceCategory
    tier: ProviderTier
    collected_at: datetime
    quality: DataQualityScore
    is_cached: bool = False


@dataclass(frozen=True, slots=True)
class CollectedDataset[T]:
    """A single provider result plus its provenance/quality envelope."""

    data: T
    metadata: CollectionMetadata
