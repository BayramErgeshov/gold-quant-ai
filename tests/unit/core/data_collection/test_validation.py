"""Unit tests for `src.core.data_collection.validation`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.core.data_collection.models import DataQualityGrade
from src.core.data_collection.validation import (
    compute_freshness,
    compute_quality_score,
    grade_from_score,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("score", "expected_grade"),
    [
        (1.0, DataQualityGrade.AAA),
        (0.95, DataQualityGrade.AAA),
        (0.92, DataQualityGrade.AA),
        (0.85, DataQualityGrade.A),
        (0.75, DataQualityGrade.BBB),
        (0.65, DataQualityGrade.BB),
        (0.55, DataQualityGrade.B),
        (0.2, DataQualityGrade.C),
    ],
)
def test_grade_from_score(score: float, expected_grade: DataQualityGrade) -> None:
    assert grade_from_score(score) == expected_grade


def test_compute_quality_score_perfect_inputs_yield_aaa() -> None:
    result = compute_quality_score(
        freshness=1.0, completeness=1.0, reliability=1.0, consistency=1.0, accuracy=1.0
    )

    assert result.overall == pytest.approx(1.0)
    assert result.grade == DataQualityGrade.AAA


def test_compute_quality_score_zero_inputs_yield_c() -> None:
    result = compute_quality_score(
        freshness=0.0, completeness=0.0, reliability=0.0, consistency=0.0, accuracy=0.0
    )

    assert result.overall == pytest.approx(0.0)
    assert result.grade == DataQualityGrade.C


def test_compute_freshness_is_full_for_current_timestamp() -> None:
    # `datetime.now(UTC)` is captured slightly before `compute_freshness`'s
    # own internal `now()`, so a few microseconds of real elapsed time are
    # unavoidable — assert near-1.0 rather than an exact real-clock match.
    assert compute_freshness(datetime.now(UTC), max_age=timedelta(hours=1)) == pytest.approx(
        1.0, abs=0.001
    )


def test_compute_freshness_decays_linearly() -> None:
    observed_at = datetime.now(UTC) - timedelta(minutes=30)

    freshness = compute_freshness(observed_at, max_age=timedelta(hours=1))

    assert 0.4 < freshness < 0.6


def test_compute_freshness_floors_at_zero_for_stale_data() -> None:
    observed_at = datetime.now(UTC) - timedelta(days=10)

    assert compute_freshness(observed_at, max_age=timedelta(hours=1)) == 0.0
