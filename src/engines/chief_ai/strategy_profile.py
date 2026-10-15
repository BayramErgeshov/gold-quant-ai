"""Strategy Builder: apply a saved module profile to one cycle's analysis.

Per the "Complete Strategy Builder" production requirement: "Enable/
disable every analysis module independently... For each enabled module:
configure Weight, Minimum confidence, Enable/Disable." Per the user's own
clarification: module-level (the platform's existing 8 Technical
Department agents plus the 6 other department-level votes), not full
per-indicator decomposition -- this preserves the already-tested
confluence architecture (`src.core.agents.confluence.combine_agent_reports`,
`TechnicalConfluence(weights=...)`) rather than introducing new voting
logic. A profile that does not list a given module leaves that module at
its current default behavior (enabled, weight 1.0, no minimum
confidence) -- profiles only ever override what they explicitly list.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.core.agents.report import AgentReport
from src.core.technical_analysis.agent import TechnicalAgent

# The 8 individual Technical Department agents (`TechnicalAgent.name`).
TECHNICAL_AGENT_MODULE_NAMES: tuple[str, ...] = (
    "market_structure",
    "trend",
    "volatility",
    "support_resistance",
    "liquidity",
    "smart_money",
    "price_action",
    "momentum",
)

# The remaining department-level votes (`ChiefAIInput.department_votes` keys /
# `ChiefAIInput.department_reliability` keys) that are not individual
# Technical Department agents.
DEPARTMENT_MODULE_NAMES: tuple[str, ...] = (
    "historical",
    "ml",
    "correlation",
    "order_flow",
    "macro",
    "news",
)

# Every module the Strategy Builder can enable/disable/weight.
MODULE_NAMES: tuple[str, ...] = TECHNICAL_AGENT_MODULE_NAMES + DEPARTMENT_MODULE_NAMES


@dataclass(frozen=True, slots=True)
class ModuleSetting:
    """One module's resolved override for a single analysis cycle.

    A plain, DB-independent value object -- the engine layer never
    depends on `src.models.strategy_profile`'s ORM classes directly
    (Hexagonal Architecture / Domain Separation), callers translate a
    persisted `StrategyProfile`'s rows into `dict[str, ModuleSetting]`.

    Attributes:
        enabled: Whether this module contributes to the decision at all.
        weight: Relative weight applied to this module's vote when enabled.
        min_confidence: Minimum confidence (0.0-1.0) this module's own
            report must clear to be counted this cycle. None means no
            module-specific floor.
    """

    enabled: bool = True
    weight: float = 1.0
    min_confidence: float | None = None


def apply_profile_to_agents(
    agents: list[TechnicalAgent], modules: dict[str, ModuleSetting]
) -> list[TechnicalAgent]:
    """Filter out Technical Department agents this profile disables.

    Args:
        agents: Every configured technical agent (e.g. the Intraday or
            Swing engine's own agent list).
        modules: This cycle's resolved per-module settings, keyed by
            `MODULE_NAMES`. An agent whose name is absent here is left
            enabled -- profiles only override what they list.

    Returns:
        `agents`, with any explicitly-disabled agent removed. Order is preserved.
    """
    return [agent for agent in agents if modules.get(agent.name, ModuleSetting()).enabled]


def filter_reports_by_min_confidence(
    reports: list[AgentReport], modules: dict[str, ModuleSetting]
) -> list[AgentReport]:
    """Drop reports that fall short of their module's configured minimum confidence.

    Args:
        reports: Every agent's own `AgentReport` for this cycle.
        modules: This cycle's resolved per-module settings.

    Returns:
        `reports`, minus any report whose `confidence` is below its
        module's `min_confidence` (when one is configured). A report
        whose module has no configured minimum, or whose module is
        unlisted, always passes through.
    """
    kept = []
    for report in reports:
        setting = modules.get(report.agent_name, ModuleSetting())
        if setting.min_confidence is not None and report.confidence < setting.min_confidence:
            continue
        kept.append(report)
    return kept


def profile_agent_weights(modules: dict[str, ModuleSetting]) -> dict[str, float]:
    """Build the `weights` dict `TechnicalConfluence`/`combine_agent_reports` expect.

    Args:
        modules: This cycle's resolved per-module settings.

    Returns:
        `{agent_name: weight}` for every enabled module listed in
        `TECHNICAL_AGENT_MODULE_NAMES`. A module absent here (or disabled)
        contributes no override -- `combine_agent_reports` already
        defaults an unlisted agent to weight 1.0, and a disabled agent's
        report was already excluded by `apply_profile_to_agents`.
    """
    return {
        name: modules[name].weight
        for name in TECHNICAL_AGENT_MODULE_NAMES
        if name in modules and modules[name].enabled
    }


def apply_profile_to_department_reliability(
    base_reliability: dict[str, float], modules: dict[str, ModuleSetting]
) -> dict[str, float]:
    """Fold a profile's department-level enable/disable/weight into reliability scores.

    Per the plan's reuse strategy: `compute_department_confidence`
    already treats `department_reliability` as each department's
    weighting factor in a reliability-weighted average (zero reliability
    contributes zero weight -- functionally the same as excluding that
    department this cycle), so disabling a department is expressed as a
    weight of 0.0 rather than new filtering logic.

    Args:
        base_reliability: This cycle's own measured reliability scores
            (`src.engines.learning_engine.department_performance`),
            before any profile override.
        modules: This cycle's resolved per-module settings.

    Returns:
        A new dict: for every name in `DEPARTMENT_MODULE_NAMES` that this
        profile lists, disabled becomes weight 0.0 and enabled becomes
        `base_reliability.get(name, 1.0) * weight`. Names the profile
        does not list keep their `base_reliability` value unchanged.
    """
    resolved = dict(base_reliability)
    for name in DEPARTMENT_MODULE_NAMES:
        setting = modules.get(name)
        if setting is None:
            continue
        resolved[name] = (
            0.0 if not setting.enabled else base_reliability.get(name, 1.0) * setting.weight
        )
    return resolved
