"""Unit tests for `src.core.agents.report`."""

from __future__ import annotations

import pytest

from src.core.agents.report import AgentReport

pytestmark = pytest.mark.unit


def test_agent_report_defaults_are_empty_collections() -> None:
    report = AgentReport(agent_name="test", bias="neutral", confidence=0.5)

    assert report.supporting_evidence == []
    assert report.opposing_evidence == []
    assert report.unknowns == []
    assert report.metrics == {}
