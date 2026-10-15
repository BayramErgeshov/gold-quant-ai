"""Unit tests for the Strategy Builder engine (`src.engines.chief_ai.strategy_profile`)."""

from __future__ import annotations

from src.core.agents.report import AgentReport
from src.core.technical_analysis.agent import TechnicalAgent
from src.engines.chief_ai.strategy_profile import (
    DEPARTMENT_MODULE_NAMES,
    MODULE_NAMES,
    TECHNICAL_AGENT_MODULE_NAMES,
    ModuleSetting,
    apply_profile_to_agents,
    apply_profile_to_department_reliability,
    filter_reports_by_min_confidence,
    profile_agent_weights,
)
from src.models.candle import Candle


class _StubAgent(TechnicalAgent):
    def __init__(self, name: str) -> None:
        self.name = name

    def analyze(self, candles: list[Candle]) -> AgentReport:
        raise NotImplementedError


def _report(agent_name: str, *, confidence: float) -> AgentReport:
    return AgentReport(agent_name=agent_name, bias="bullish", confidence=confidence)


def test_module_names_has_no_duplicates_and_covers_technical_plus_department() -> None:
    assert len(MODULE_NAMES) == len(set(MODULE_NAMES))
    assert set(MODULE_NAMES) == set(TECHNICAL_AGENT_MODULE_NAMES) | set(DEPARTMENT_MODULE_NAMES)


def test_apply_profile_to_agents_removes_only_explicitly_disabled_agents() -> None:
    agents: list[TechnicalAgent] = [
        _StubAgent("trend"),
        _StubAgent("momentum"),
        _StubAgent("liquidity"),
    ]
    modules = {
        "trend": ModuleSetting(enabled=True),
        "momentum": ModuleSetting(enabled=False),
        # "liquidity" is unlisted -- must stay enabled by default.
    }

    result = apply_profile_to_agents(agents, modules)

    assert [agent.name for agent in result] == ["trend", "liquidity"]


def test_apply_profile_to_agents_with_no_modules_keeps_every_agent() -> None:
    agents: list[TechnicalAgent] = [_StubAgent("trend"), _StubAgent("momentum")]

    result = apply_profile_to_agents(agents, {})

    assert result == agents


def test_filter_reports_by_min_confidence_drops_reports_below_the_floor() -> None:
    reports = [_report("trend", confidence=0.9), _report("momentum", confidence=0.4)]
    modules = {"momentum": ModuleSetting(min_confidence=0.6)}

    result = filter_reports_by_min_confidence(reports, modules)

    assert [report.agent_name for report in result] == ["trend"]


def test_filter_reports_by_min_confidence_keeps_reports_at_or_above_the_floor() -> None:
    reports = [_report("trend", confidence=0.6)]
    modules = {"trend": ModuleSetting(min_confidence=0.6)}

    result = filter_reports_by_min_confidence(reports, modules)

    assert len(result) == 1


def test_profile_agent_weights_includes_only_enabled_technical_modules() -> None:
    modules = {
        "trend": ModuleSetting(enabled=True, weight=2.0),
        "momentum": ModuleSetting(enabled=False, weight=3.0),
        "correlation": ModuleSetting(enabled=True, weight=1.5),
    }

    weights = profile_agent_weights(modules)

    assert weights == {"trend": 2.0}


def test_apply_profile_to_department_reliability_zeroes_a_disabled_department() -> None:
    base_reliability = {"historical": 0.8, "ml": 0.6}
    modules = {"historical": ModuleSetting(enabled=False)}

    resolved = apply_profile_to_department_reliability(base_reliability, modules)

    assert resolved["historical"] == 0.0
    assert resolved["ml"] == 0.6


def test_apply_profile_to_department_reliability_scales_an_enabled_department() -> None:
    base_reliability = {"correlation": 0.5}
    modules = {"correlation": ModuleSetting(enabled=True, weight=2.0)}

    resolved = apply_profile_to_department_reliability(base_reliability, modules)

    assert resolved["correlation"] == 1.0


def test_apply_profile_to_department_reliability_defaults_unmeasured_department_to_one() -> None:
    modules = {"news": ModuleSetting(enabled=True, weight=0.5)}

    resolved = apply_profile_to_department_reliability({}, modules)

    assert resolved["news"] == 0.5


def test_apply_profile_to_department_reliability_leaves_unlisted_departments_untouched() -> None:
    base_reliability = {"macro": 0.9}

    resolved = apply_profile_to_department_reliability(base_reliability, {})

    assert resolved == {"macro": 0.9}
