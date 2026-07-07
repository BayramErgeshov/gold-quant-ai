"""Unit tests for `src.core.agents.confluence`."""

from __future__ import annotations

import pytest

from src.core.agents.confluence import combine_agent_reports, grade_from_confidence
from src.core.agents.report import AgentReport

pytestmark = pytest.mark.unit


def _report(agent_name: str, bias: str, confidence: float, **kwargs: object) -> AgentReport:
    return AgentReport(agent_name=agent_name, bias=bias, confidence=confidence, **kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("confidence", "expected_grade"),
    [(0.9, "AAA"), (0.8, "AA"), (0.7, "A"), (0.6, "BBB"), (0.5, "BB"), (0.4, "B"), (0.1, "C")],
)
def test_grade_from_confidence(confidence: float, expected_grade: str) -> None:
    assert grade_from_confidence(confidence) == expected_grade


def test_combine_with_no_reports_returns_fully_neutral() -> None:
    result = combine_agent_reports([])

    assert result.neutral_probability == 1.0
    assert result.confidence == 0.0
    assert result.quality_grade == "C"
    assert result.agent_reports == []


def test_combine_unanimous_bullish_reports() -> None:
    reports = [_report("a", "bullish", 0.8), _report("b", "bullish", 0.6)]

    result = combine_agent_reports(reports)

    assert result.bullish_probability == pytest.approx(1.0)
    assert result.confidence == pytest.approx(0.7)


def test_combine_all_zero_confidence_yields_fully_neutral() -> None:
    reports = [_report("a", "bullish", 0.0), _report("b", "bearish", 0.0)]

    result = combine_agent_reports(reports)

    assert result.neutral_probability == 1.0


def test_combine_respects_custom_weights() -> None:
    reports = [_report("a", "bullish", 0.5), _report("b", "bearish", 0.5)]

    result = combine_agent_reports(reports, weights={"a": 0.1, "b": 10.0})

    assert result.bearish_probability > result.bullish_probability


def test_combine_blends_historical_win_rate() -> None:
    reports = [_report("a", "bullish", 0.5)]

    result = combine_agent_reports(reports, historical_win_rate=0.9)

    assert result.historical_win_rate == 0.9
    assert result.confidence == pytest.approx((0.5 + 0.9) / 2)


def test_combine_pools_evidence() -> None:
    reports = [
        _report("a", "bullish", 0.8, supporting_evidence=["support A"]),
        _report("b", "bearish", 0.3, opposing_evidence=["oppose B"]),
    ]

    result = combine_agent_reports(reports)

    assert "support A" in result.strongest_supporting_factors
    assert "oppose B" in result.strongest_opposing_factors
