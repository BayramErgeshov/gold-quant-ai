"""Unit tests for probability calibration diagnostics."""

from __future__ import annotations

import pytest

from src.core.ml.calibration import compute_brier_score, compute_calibration_buckets

pytestmark = pytest.mark.unit


def test_brier_score_is_zero_for_perfect_predictions() -> None:
    assert compute_brier_score([1.0, 0.0, 1.0], [True, False, True]) == 0.0


def test_brier_score_is_one_for_worst_predictions() -> None:
    assert compute_brier_score([0.0, 1.0], [True, False]) == 1.0


def test_brier_score_is_zero_for_empty_input() -> None:
    assert compute_brier_score([], []) == 0.0


def test_brier_score_raises_for_mismatched_lengths() -> None:
    with pytest.raises(ValueError, match="same length"):
        compute_brier_score([0.5], [True, False])


def test_calibration_buckets_group_by_probability_range() -> None:
    probabilities = [0.05, 0.15, 0.85, 0.95]
    outcomes = [False, True, True, True]

    buckets = compute_calibration_buckets(probabilities, outcomes, n_buckets=10)

    assert len(buckets) == 4
    assert buckets[0].lower_bound == 0.0
    assert buckets[0].count == 1


def test_calibration_buckets_report_predicted_and_observed_rates() -> None:
    probabilities = [0.9, 0.9, 0.9]
    outcomes = [True, True, False]

    buckets = compute_calibration_buckets(probabilities, outcomes, n_buckets=10)

    assert len(buckets) == 1
    assert buckets[0].predicted_mean == pytest.approx(0.9)
    assert buckets[0].observed_rate == pytest.approx(2 / 3)
    assert buckets[0].count == 3


def test_calibration_buckets_omit_empty_buckets() -> None:
    buckets = compute_calibration_buckets([0.5], [True], n_buckets=10)

    assert len(buckets) == 1


def test_calibration_buckets_clamps_probability_of_one_into_last_bucket() -> None:
    buckets = compute_calibration_buckets([1.0], [True], n_buckets=10)

    assert len(buckets) == 1
    assert buckets[0].lower_bound == pytest.approx(0.9)


def test_calibration_buckets_raises_for_mismatched_lengths() -> None:
    with pytest.raises(ValueError, match="same length"):
        compute_calibration_buckets([0.5], [True, False])
