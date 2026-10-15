"""Unit tests for `src.engines.historical_engine.similarity`."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.engines.historical_engine.regime_detection import RegimeFeatures
from src.engines.historical_engine.similarity import (
    FeatureWeights,
    SimilarityMatch,
    compute_outcome_statistics,
    compute_similarity,
    find_similar_windows,
    summarize_matches_for_direction,
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

    ignoring_trend = compute_similarity(query, candidate, weights=FeatureWeights(trend_weight=0.0))
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


def _match(
    *, outcome: float | None, adverse_long: float | None = None, adverse_short: float | None = None
) -> SimilarityMatch:
    return SimilarityMatch(
        timestamp=_BASE_TIME,
        similarity_score=0.9,
        features=_features(),
        outcome_return_pct=outcome,
        adverse_if_long_pct=adverse_long,
        adverse_if_short_pct=adverse_short,
    )


def test_summarize_matches_for_direction_excludes_matches_without_a_measured_outcome() -> None:
    matches = [_match(outcome=None), _match(outcome=1.0, adverse_long=0.5, adverse_short=0.1)]

    stats = summarize_matches_for_direction(matches, "buy", forward_bars=10, timeframe="M15")

    assert stats.found_count == 1


def test_summarize_matches_for_direction_counts_profitable_and_failed_for_buy() -> None:
    matches = [
        _match(outcome=2.0, adverse_long=0.5, adverse_short=1.0),
        _match(outcome=-1.0, adverse_long=1.5, adverse_short=0.2),
        _match(outcome=0.0, adverse_long=0.3, adverse_short=0.3),
    ]

    stats = summarize_matches_for_direction(matches, "buy", forward_bars=10, timeframe="M15")

    assert stats.found_count == 3
    assert stats.profitable_count == 1
    assert stats.failed_count == 2
    assert stats.win_rate_pct == pytest.approx(100 / 3)


def test_summarize_matches_for_direction_flips_favorability_for_sell() -> None:
    matches = [
        _match(outcome=2.0, adverse_long=0.5, adverse_short=1.0),
        _match(outcome=-1.0, adverse_long=1.5, adverse_short=0.2),
    ]

    stats = summarize_matches_for_direction(matches, "sell", forward_bars=10, timeframe="M15")

    # A -1.0% raw return favors a SELL (price fell); the +2.0% one does not.
    assert stats.profitable_count == 1
    assert stats.failed_count == 1


def test_summarize_matches_for_direction_computes_average_rr_and_drawdown() -> None:
    matches = [
        # Favorable move +2.0%, adverse (against BUY) 0.5% -> RR = 4.0.
        _match(outcome=2.0, adverse_long=0.5, adverse_short=1.0),
        # Favorable move +4.0%, adverse (against BUY) 2.0% -> RR = 2.0.
        _match(outcome=4.0, adverse_long=2.0, adverse_short=0.1),
    ]

    stats = summarize_matches_for_direction(matches, "buy", forward_bars=10, timeframe="M15")

    assert stats.average_rr == pytest.approx(3.0)
    assert stats.average_drawdown_pct == pytest.approx(1.25)


def test_summarize_matches_for_direction_holding_time_reflects_forward_bars_and_timeframe() -> None:
    stats = summarize_matches_for_direction([], "buy", forward_bars=10, timeframe="M15")

    assert stats.average_holding_time_minutes == pytest.approx(150.0)
    assert stats.found_count == 0
    assert stats.win_rate_pct is None
    assert stats.average_rr is None
    assert stats.average_drawdown_pct is None


def test_summarize_matches_for_direction_skips_rr_for_zero_adverse_excursion() -> None:
    matches = [_match(outcome=2.0, adverse_long=0.0, adverse_short=0.0)]

    stats = summarize_matches_for_direction(matches, "buy", forward_bars=10, timeframe="M15")

    # A zero adverse excursion means "never moved against the trade" --
    # an undefined (infinite) RR, honestly excluded rather than divided
    # by zero or fabricated.
    assert stats.average_rr is None
    assert stats.average_drawdown_pct == pytest.approx(0.0)
