"""Unit tests for `MarketScanner`'s pure-function helpers."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.core.execution.mt5_client import OpenPosition
from src.engines.correlation_engine.analysis import CorrelationAnalysisResult
from src.engines.historical_engine.similarity import OutcomeStatistics
from src.engines.order_flow_engine.service import OrderFlowResult
from src.workflows.market_update.pipeline import (
    _correlation_vote_from_result,
    _order_flow_vote_from_result,
    exposure_state_from_positions,
    historical_vote_from_outcome,
    ml_vote_from_prediction,
)

pytestmark = pytest.mark.unit


def testhistorical_vote_from_outcome_with_no_samples_is_neutral() -> None:
    vote = historical_vote_from_outcome(
        OutcomeStatistics(
            sample_size=0,
            win_rate=0.0,
            average_return_pct=0.0,
            median_return_pct=0.0,
            max_return_pct=0.0,
            min_return_pct=0.0,
        )
    )

    assert vote.confidence == 0.0
    assert vote.neutral_probability == 1.0
    assert vote.strongest_opposing_factors == ["no_historical_analogues_found"]


def testhistorical_vote_from_outcome_scales_confidence_by_sample_size() -> None:
    small_sample = historical_vote_from_outcome(
        OutcomeStatistics(
            sample_size=10,
            win_rate=1.0,
            average_return_pct=2.0,
            median_return_pct=2.0,
            max_return_pct=3.0,
            min_return_pct=1.0,
        )
    )
    large_sample = historical_vote_from_outcome(
        OutcomeStatistics(
            sample_size=100,
            win_rate=1.0,
            average_return_pct=2.0,
            median_return_pct=2.0,
            max_return_pct=3.0,
            min_return_pct=1.0,
        )
    )

    assert small_sample.bullish_probability == 1.0
    assert large_sample.confidence > small_sample.confidence
    assert large_sample.confidence == pytest.approx(1.0)


def testml_vote_from_prediction_combines_strong_and_regular_labels() -> None:
    vote = ml_vote_from_prediction(
        {"strong_bullish": 0.5, "bullish": 0.3, "neutral": 0.1, "bearish": 0.1},
        forward_return_pct=1.5,
    )

    assert vote.bullish_probability == pytest.approx(0.8)
    assert vote.bearish_probability == pytest.approx(0.1)
    assert vote.confidence == pytest.approx(0.5)
    assert "ml_predicted_forward_return:+1.50%" in vote.strongest_supporting_factors


def testml_vote_from_prediction_negative_return_is_opposing_evidence() -> None:
    vote = ml_vote_from_prediction({"bearish": 0.6, "neutral": 0.4}, forward_return_pct=-0.8)

    assert vote.strongest_opposing_factors == ["ml_predicted_forward_return:-0.80%"]
    assert vote.strongest_supporting_factors == []


def test_exposure_state_from_positions_is_zero_when_equity_non_positive() -> None:
    state = exposure_state_from_positions([], equity=0.0)

    assert state.total_exposure_pct == 0.0
    assert state.instrument_exposure_pct == 0.0


def test_exposure_state_from_positions_computes_risk_pct_of_equity() -> None:
    # 2.0 units at a $10 stop distance risks $20 of a $10,000 account: 0.2%.
    # Exposure is capital-at-risk, not notional/leveraged position value —
    # a correctly risk-sized CFD position routinely has notional value far
    # exceeding equity, which would make a notional-based exposure limit
    # meaningless.
    position = OpenPosition(
        ticket="1",
        symbol="XAUUSD",
        direction="buy",
        volume=2.0,
        entry_price=2000.0,
        stop_loss=1990.0,
        take_profit=None,
        current_price=2100.0,
        profit=200.0,
        magic_number=1,
        opened_at=datetime.now(UTC),
    )

    state = exposure_state_from_positions([position], equity=10_000.0)

    assert state.total_exposure_pct == pytest.approx(0.2)
    assert state.instrument_exposure_pct == pytest.approx(0.2)


def test_correlation_vote_is_neutral_with_no_instruments_configured() -> None:
    vote = _correlation_vote_from_result(
        CorrelationAnalysisResult(xauusd_regime=None, dxy_proxy=None, instruments=[])
    )

    assert vote.confidence == 0.0
    assert vote.neutral_probability == 1.0
    assert vote.strongest_opposing_factors == ["no_correlated_instruments_configured"]


def test_order_flow_vote_maps_bullish_probability_and_confidence() -> None:
    result = OrderFlowResult(
        source="synthetic",
        bullish_probability=0.4,
        bearish_probability=0.1,
        confidence=0.4,
        supporting_evidence=["Price is above VWAP (2000.00)"],
        opposing_evidence=[],
    )

    vote = _order_flow_vote_from_result(result)

    assert vote.bullish_probability == 0.4
    assert vote.bearish_probability == 0.1
    assert vote.neutral_probability == pytest.approx(0.5)
    assert vote.confidence == 0.4
    assert vote.strongest_supporting_factors == [
        "order_flow[synthetic]: Price is above VWAP (2000.00)"
    ]
