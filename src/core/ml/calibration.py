"""Probability calibration diagnostics for the Machine Learning Engine.

Per MACHINE_LEARNING_ENGINE.md "Calibration"/"Model Monitoring": measures
whether a model's predicted probabilities match observed outcome
frequencies. A well-calibrated model that says "70% bullish" should be
right about 70% of the time across many such predictions.
"""

from __future__ import annotations

from dataclasses import dataclass


def compute_brier_score(predicted_probabilities: list[float], outcomes: list[bool]) -> float:
    """Compute the Brier score for a set of binary predictions.

    Args:
        predicted_probabilities: Predicted probability of the positive
            outcome for each sample, in [0.0, 1.0].
        outcomes: Whether the positive outcome actually occurred, per sample.

    Returns:
        Mean squared error between predicted probability and actual
        outcome (0.0 = perfect, 1.0 = worst possible). 0.0 if there are no
        samples.

    Raises:
        ValueError: If the two lists have different lengths.
    """
    if len(predicted_probabilities) != len(outcomes):
        raise ValueError("predicted_probabilities and outcomes must be the same length")
    if not predicted_probabilities:
        return 0.0

    squared_errors = [
        (probability - float(outcome)) ** 2
        for probability, outcome in zip(predicted_probabilities, outcomes, strict=True)
    ]
    return sum(squared_errors) / len(squared_errors)


@dataclass(frozen=True, slots=True)
class CalibrationBucket:
    """One probability bucket's predicted vs. observed outcome rate.

    Attributes:
        lower_bound: Bucket's inclusive lower probability bound.
        upper_bound: Bucket's exclusive upper probability bound.
        predicted_mean: Average predicted probability within the bucket.
        observed_rate: Actual fraction of positive outcomes within the bucket.
        count: Number of samples in the bucket.
    """

    lower_bound: float
    upper_bound: float
    predicted_mean: float
    observed_rate: float
    count: int


def compute_calibration_buckets(
    predicted_probabilities: list[float], outcomes: list[bool], *, n_buckets: int = 10
) -> list[CalibrationBucket]:
    """Group predictions into probability buckets and compare to observed rates.

    Args:
        predicted_probabilities: Predicted probability of the positive
            outcome for each sample, in [0.0, 1.0].
        outcomes: Whether the positive outcome actually occurred, per sample.
        n_buckets: Number of equal-width buckets across [0.0, 1.0].

    Returns:
        One `CalibrationBucket` per non-empty bucket, ordered by
        `lower_bound` ascending. Empty buckets are omitted rather than
        reported with a fabricated 0.0 observed rate.

    Raises:
        ValueError: If the two lists have different lengths.
    """
    if len(predicted_probabilities) != len(outcomes):
        raise ValueError("predicted_probabilities and outcomes must be the same length")

    bucket_width = 1.0 / n_buckets
    grouped: dict[int, list[tuple[float, bool]]] = {}
    for probability, outcome in zip(predicted_probabilities, outcomes, strict=True):
        bucket_index = min(int(probability / bucket_width), n_buckets - 1)
        grouped.setdefault(bucket_index, []).append((probability, outcome))

    buckets: list[CalibrationBucket] = []
    for bucket_index in sorted(grouped):
        entries = grouped[bucket_index]
        predicted_mean = sum(probability for probability, _ in entries) / len(entries)
        observed_rate = sum(1 for _, outcome in entries if outcome) / len(entries)
        buckets.append(
            CalibrationBucket(
                lower_bound=bucket_index * bucket_width,
                upper_bound=(bucket_index + 1) * bucket_width,
                predicted_mean=predicted_mean,
                observed_rate=observed_rate,
                count=len(entries),
            )
        )
    return buckets
