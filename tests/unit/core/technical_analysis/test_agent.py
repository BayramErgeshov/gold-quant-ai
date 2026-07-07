"""Unit tests for `src.core.technical_analysis.agent`."""

from __future__ import annotations

import pytest

from src.core.technical_analysis.agent import AgentReport, TechnicalAgent

pytestmark = pytest.mark.unit


def test_agent_report_defaults_are_empty_collections() -> None:
    report = AgentReport(agent_name="test", bias="neutral", confidence=0.5)

    assert report.supporting_evidence == []
    assert report.opposing_evidence == []
    assert report.unknowns == []
    assert report.metrics == {}


def test_technical_agent_cannot_be_instantiated_directly() -> None:
    with pytest.raises(TypeError):
        TechnicalAgent()  # type: ignore[abstract]
