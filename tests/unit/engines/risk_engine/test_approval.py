"""Unit tests for the trade approval pipeline."""

from __future__ import annotations

import pytest

from src.engines.risk_engine.approval import (
    TradeApprovalRequest,
    classify_confidence_level,
    evaluate_trade,
)

pytestmark = pytest.mark.unit


def _base_request(**overrides: object) -> TradeApprovalRequest:
    defaults: dict[str, object] = {
        "confidence_pct": 80.0,
        "spread_pips": 1.0,
        "max_spread_pips": 3.0,
        "is_market_open": True,
        "historical_edge_pct": 0.5,
        "min_historical_edge_pct": 0.2,
    }
    defaults.update(overrides)
    return TradeApprovalRequest(**defaults)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("confidence_pct", "expected_level"),
    [
        (0.0, "reject"),
        (40.0, "reject"),
        (41.0, "observation_only"),
        (60.0, "observation_only"),
        (61.0, "possible_setup"),
        (75.0, "possible_setup"),
        (76.0, "high_quality"),
        (85.0, "high_quality"),
        (86.0, "institutional_grade"),
        (100.0, "institutional_grade"),
    ],
)
def test_classify_confidence_level_boundaries(
    confidence_pct: float, expected_level: str
) -> None:
    assert classify_confidence_level(confidence_pct) == expected_level


def test_classify_confidence_level_raises_out_of_range() -> None:
    with pytest.raises(ValueError, match="confidence_pct"):
        classify_confidence_level(101.0)


def test_fully_valid_request_is_approved() -> None:
    decision = evaluate_trade(_base_request())

    assert decision.approved is True
    assert decision.rejection_reasons == []
    assert decision.confidence_level == "high_quality"


def test_low_confidence_is_rejected() -> None:
    decision = evaluate_trade(_base_request(confidence_pct=50.0))

    assert decision.approved is False
    assert any("confidence_level_not_executable" in reason for reason in decision.rejection_reasons)


def test_excessive_spread_is_rejected() -> None:
    decision = evaluate_trade(_base_request(spread_pips=5.0, max_spread_pips=3.0))

    assert decision.approved is False
    assert any("spread_excessive" in reason for reason in decision.rejection_reasons)


def test_market_closed_is_rejected() -> None:
    decision = evaluate_trade(_base_request(is_market_open=False))

    assert decision.approved is False
    assert "market_closed" in decision.rejection_reasons


def test_insufficient_historical_edge_is_rejected() -> None:
    decision = evaluate_trade(
        _base_request(historical_edge_pct=0.1, min_historical_edge_pct=0.3)
    )

    assert decision.approved is False
    assert any(
        "historical_edge_insufficient" in reason for reason in decision.rejection_reasons
    )


def test_critical_news_imminent_is_rejected() -> None:
    decision = evaluate_trade(_base_request(critical_news_imminent=True))

    assert decision.approved is False
    assert "critical_news_imminent" in decision.rejection_reasons


def test_incomplete_data_is_rejected() -> None:
    decision = evaluate_trade(_base_request(data_complete=False))

    assert decision.approved is False
    assert "data_incomplete" in decision.rejection_reasons


def test_degraded_system_health_is_rejected() -> None:
    decision = evaluate_trade(_base_request(system_health_ok=False))

    assert decision.approved is False
    assert "system_health_degraded" in decision.rejection_reasons


def test_exposure_breaches_are_included_in_rejection_reasons() -> None:
    decision = evaluate_trade(_base_request(exposure_breaches=["total_exposure_exceeded: x"]))

    assert decision.approved is False
    assert "total_exposure_exceeded: x" in decision.rejection_reasons


def test_multiple_failures_are_all_reported() -> None:
    decision = evaluate_trade(
        _base_request(is_market_open=False, critical_news_imminent=True)
    )

    assert decision.approved is False
    assert len(decision.rejection_reasons) == 2
