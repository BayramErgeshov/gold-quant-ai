"""Unit tests for `MacroConfluence`."""

from __future__ import annotations

import pytest

from src.core.agents.report import AgentReport
from src.engines.macro_engine.confluence import MacroConfluence

pytestmark = pytest.mark.unit


def _report(agent_name: str, bias: str, confidence: float) -> AgentReport:
    return AgentReport(agent_name=agent_name, bias=bias, confidence=confidence)  # type: ignore[arg-type]


def test_combine_with_no_reports_returns_fully_neutral() -> None:
    result = MacroConfluence().combine([])

    assert result.neutral_probability == 1.0
    assert result.macro_confidence == 0.0
    assert result.macro_quality_grade == "C"


def test_combine_unanimous_bullish_reports() -> None:
    reports = [_report("inflation", "bullish", 0.8), _report("employment", "bullish", 0.6)]

    result = MacroConfluence().combine(reports)

    assert result.bullish_probability == pytest.approx(1.0)
    assert result.macro_confidence == pytest.approx(0.7)


def test_combine_respects_custom_weights() -> None:
    reports = [_report("interest_rate", "bullish", 0.5), _report("dxy", "bearish", 0.5)]

    result = MacroConfluence(weights={"interest_rate": 0.1, "dxy": 10.0}).combine(reports)

    assert result.bearish_probability > result.bullish_probability


def test_combine_pools_agent_reports() -> None:
    reports = [_report("inflation", "bullish", 0.5)]

    result = MacroConfluence().combine(reports)

    assert result.agent_reports == reports
