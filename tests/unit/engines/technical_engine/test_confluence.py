"""Unit tests for `TechnicalConfluence`."""

from __future__ import annotations

import pytest

from src.core.technical_analysis.agent import AgentReport
from src.engines.historical_engine.similarity import OutcomeStatistics
from src.engines.technical_engine.confluence import TechnicalConfluence

pytestmark = pytest.mark.unit


def _report(agent_name: str, bias: str, confidence: float, **kwargs: object) -> AgentReport:
    return AgentReport(agent_name=agent_name, bias=bias, confidence=confidence, **kwargs)  # type: ignore[arg-type]


def test_combine_with_no_reports_returns_fully_neutral() -> None:
    result = TechnicalConfluence().combine([])

    assert result.neutral_probability == 1.0
    assert result.bullish_probability == 0.0
    assert result.technical_confidence == 0.0
    assert result.technical_quality_grade == "C"


def test_combine_unanimous_bullish_reports() -> None:
    reports = [
        _report("trend", "bullish", 0.8),
        _report("market_structure", "bullish", 0.7),
    ]

    result = TechnicalConfluence().combine(reports)

    assert result.bullish_probability == pytest.approx(1.0)
    assert result.bearish_probability == 0.0
    assert result.technical_confidence == pytest.approx(0.75)


def test_combine_mixed_reports_weighted_by_confidence() -> None:
    reports = [
        _report("trend", "bullish", 0.8),
        _report("liquidity", "bearish", 0.2),
    ]

    result = TechnicalConfluence().combine(reports)

    assert result.bullish_probability > result.bearish_probability


def test_combine_all_zero_confidence_reports_yields_fully_neutral() -> None:
    reports = [
        _report("trend", "bullish", 0.0),
        _report("liquidity", "bearish", 0.0),
    ]

    result = TechnicalConfluence().combine(reports)

    assert result.neutral_probability == 1.0
    assert result.bullish_probability == 0.0
    assert result.bearish_probability == 0.0


def test_combine_all_neutral_reports_yields_zero_confidence() -> None:
    reports = [
        _report("volatility", "neutral", 1.0),
        _report("support_resistance", "neutral", 0.6),
    ]

    result = TechnicalConfluence().combine(reports)

    assert result.neutral_probability == pytest.approx(1.0)
    assert result.technical_confidence == 0.0


def test_combine_respects_custom_weights() -> None:
    reports = [
        _report("trend", "bullish", 0.5),
        _report("liquidity", "bearish", 0.5),
    ]

    weighted_toward_bearish = TechnicalConfluence(
        weights={"trend": 0.1, "liquidity": 10.0}
    ).combine(reports)

    assert weighted_toward_bearish.bearish_probability > weighted_toward_bearish.bullish_probability


def test_combine_pools_supporting_and_opposing_evidence() -> None:
    reports = [
        _report("trend", "bullish", 0.8, supporting_evidence=["Uptrend confirmed"]),
        _report("liquidity", "bearish", 0.3, opposing_evidence=["Sweep detected"]),
    ]

    result = TechnicalConfluence().combine(reports)

    assert "Uptrend confirmed" in result.strongest_supporting_factors
    assert "Sweep detected" in result.strongest_opposing_factors


def test_combine_blends_historical_outcome_into_confidence() -> None:
    reports = [_report("trend", "bullish", 0.5)]
    outcome = OutcomeStatistics(
        sample_size=10,
        win_rate=0.9,
        average_return_pct=1.0,
        median_return_pct=1.0,
        max_return_pct=2.0,
        min_return_pct=-1.0,
    )

    result = TechnicalConfluence().combine(reports, historical_outcome=outcome)

    assert result.historical_win_rate == 0.9
    assert result.technical_confidence == pytest.approx((0.5 + 0.9) / 2)


def test_combine_ignores_historical_outcome_with_zero_sample_size() -> None:
    reports = [_report("trend", "bullish", 0.5)]
    outcome = OutcomeStatistics(
        sample_size=0,
        win_rate=0.0,
        average_return_pct=0.0,
        median_return_pct=0.0,
        max_return_pct=0.0,
        min_return_pct=0.0,
    )

    result = TechnicalConfluence().combine(reports, historical_outcome=outcome)

    assert result.historical_win_rate is None
    assert result.technical_confidence == pytest.approx(0.5)


@pytest.mark.parametrize(
    ("confidence", "expected_grade"),
    [(0.9, "AAA"), (0.8, "AA"), (0.7, "A"), (0.6, "BBB"), (0.5, "BB"), (0.4, "B"), (0.1, "C")],
)
def test_combine_assigns_quality_grade_from_confidence(
    confidence: float, expected_grade: str
) -> None:
    reports = [_report("trend", "bullish", confidence)]

    result = TechnicalConfluence().combine(reports)

    assert result.technical_quality_grade == expected_grade
