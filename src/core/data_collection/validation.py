"""Data quality scoring for the Data Collection Engine.

Per DATA_QUALITY_STANDARD.md: "Every dataset receives... Freshness,
Completeness, Reliability, Consistency, Accuracy... Overall Quality."
Structural validation (schema, duplicates, outliers) is provider-specific
and lives alongside each provider; this module owns the common scoring
formula so every provider is graded identically.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from src.core.data_collection.models import DataQualityGrade, DataQualityScore

_GRADE_THRESHOLDS: tuple[tuple[float, DataQualityGrade], ...] = (
    (0.95, DataQualityGrade.AAA),
    (0.90, DataQualityGrade.AA),
    (0.80, DataQualityGrade.A),
    (0.70, DataQualityGrade.BBB),
    (0.60, DataQualityGrade.BB),
    (0.50, DataQualityGrade.B),
)

_DIMENSION_WEIGHTS = {
    "freshness": 0.15,
    "completeness": 0.25,
    "reliability": 0.25,
    "consistency": 0.15,
    "accuracy": 0.20,
}


def grade_from_score(overall: float) -> DataQualityGrade:
    """Map an overall 0.0-1.0 score to an institutional quality grade.

    Args:
        overall: Weighted-average quality score.

    Returns:
        The corresponding `DataQualityGrade`; scores below every threshold
        receive `C` (DATA_QUALITY_STANDARD.md: "C - Reject").
    """
    for threshold, grade in _GRADE_THRESHOLDS:
        if overall >= threshold:
            return grade
    return DataQualityGrade.C


def compute_quality_score(
    *,
    freshness: float,
    completeness: float,
    reliability: float,
    consistency: float,
    accuracy: float,
) -> DataQualityScore:
    """Compute the weighted overall quality score and grade.

    Args:
        freshness: How recent the data is (1.0 = collected just now).
        completeness: Fraction of expected fields/records present.
        reliability: Source's historical reliability score.
        consistency: Agreement with other independent sources, if checked.
        accuracy: Estimated correctness (e.g. cross-source validation).

    Returns:
        A fully populated `DataQualityScore`.
    """
    overall = (
        freshness * _DIMENSION_WEIGHTS["freshness"]
        + completeness * _DIMENSION_WEIGHTS["completeness"]
        + reliability * _DIMENSION_WEIGHTS["reliability"]
        + consistency * _DIMENSION_WEIGHTS["consistency"]
        + accuracy * _DIMENSION_WEIGHTS["accuracy"]
    )
    return DataQualityScore(
        freshness=freshness,
        completeness=completeness,
        reliability=reliability,
        consistency=consistency,
        accuracy=accuracy,
        overall=overall,
        grade=grade_from_score(overall),
    )


def compute_freshness(observed_at: datetime, *, max_age: timedelta) -> float:
    """Score how fresh a timestamp is, decaying linearly to 0 at `max_age`.

    Args:
        observed_at: When the underlying data point was produced/observed.
        max_age: Age at which freshness is considered fully stale (0.0).

    Returns:
        A freshness score in [0.0, 1.0].
    """
    age = datetime.now(UTC) - observed_at
    if age <= timedelta(0):
        return 1.0
    if age >= max_age:
        return 0.0
    return 1.0 - (age / max_age)
