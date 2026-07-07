"""Unit tests for `src.engines.historical_engine.similarity`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.engines.historical_engine.regime_detection import RegimeFeatures
from src.engines.historical_engine.similarity import (
    FeatureWeights,
    compute_outcome_statistics,
    compute_similarity,
    find_similar_windows,
)

pytestmark = pytest.mark.unit

_BASE_TIME = datetime(2020, 1, 1, tzinfo=UTC)


def _features(
    trend: float = 0.0, volatility: float = 0.0, range_width: float = 0.0
) -> RegimeFeatures:
    return RegimeFeatures(
        trend_slope_pct=trend, volatility_pct=volatility, range_width_pct=range_width
    )


def test_compute_similarity_is_one_for_identical_features() -> None:
    features = _features(trend=0.5, volatility=1.0, range_width=2.0)

    assert compute_similarity(features, features) == pytest.approx(1.0)


def test_compute_similarity_decreases_with_distance() -> None:
    query = _features(trend=0.0, volatility=0.0, range_width=0.0)
    close = _features(trend=0.1, volatility=0.1, range_width=0.1)
    far = _features(trend=5.0, volatility=5.0, range_width=5.0)

    assert compute_similarity(query, close) > compute_similarity(query, far)


def test_compute_similarity_respects_weights() -> None:
    query = _features(trend=0.0, volatility=0.0, range_width=0.0)
    candidate = _features(trend=1.0, volatility=0.0, range_width=0.0)

    ignoring_trend = compute_similarity(
        query, candidate, weights=FeatureWeights(trend_weight=0.0)
    )
    weighting_trend = compute_similarity(
        query, candidate, weights=FeatureWeights(trend_weight=10.0)
    )

    assert ignoring_trend == pytest.approx(1.0)
    assert weighting_trend < ignoring_trend


def test_find_similar_windows_ranks_most_similar_first() -> None:
    query = _features(trend=0.0, volatility=0.0, range_width=0.0)
    candidates = [
        (_BASE_TIME, _features(trend=5.0)),
        (_BASE_TIME + timedelta(days=1), _features(trend=0.01)),
        (_BASE_TIME + timedelta(days=2), _features(trend=2.0)),
    ]

    matches = find_similar_windows(query, candidates, top_n=10)

    assert [match.timestamp for match in matches] == [
        _BASE_TIME + timedelta(days=1),
        _BASE_TIME + timedelta(days=2),
        _BASE_TIME,
    ]


def test_find_similar_windows_respects_top_n() -> None:
    query = _features()
    candidates = [(_BASE_TIME + timedelta(days=i), _features(trend=float(i))) for i in range(10)]

    matches = find_similar_windows(query, candidates, top_n=3)

    assert len(matches) == 3


def test_compute_outcome_statistics_empty_input() -> None:
    stats = compute_outcome_statistics([])

    assert stats.sample_size == 0
    assert stats.win_rate == 0.0


def test_compute_outcome_statistics_computes_expected_values() -> None:
    stats = compute_outcome_statistics([2.0, -1.0, 3.0, -2.0])

    assert stats.sample_size == 4
    assert stats.win_rate == 0.5
    assert stats.average_return_pct == pytest.approx(0.5)
    assert stats.max_return_pct == 3.0
    assert stats.min_return_pct == -2.0
