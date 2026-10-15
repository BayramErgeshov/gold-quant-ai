"""Aggregate statistics over a walk-forward validation run.

Per the "Historical Walk-Forward Validation" production requirement:
"Produce statistics on which confirmation combinations worked/failed and
which departments helped/hurt." Mirrors
`src.engines.learning_engine.department_performance`'s own win/loss
contribution-rate concept, applied to `WalkForwardOpportunity` records
instead of closed `Trade` rows -- the same idea of "how often was this
department part of the winning/losing consensus," just measured against
simulated rather than real outcomes.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from src.engines.validation_engine.walk_forward import WalkForwardOpportunity


@dataclass(frozen=True, slots=True)
class DepartmentComboStatistics:
    """One specific combination of agreeing departments' measured outcome.

    Attributes:
        departments: The sorted combination of departments that agreed
            (empty tuple means no department cast a directional vote
            agreeing with the traded direction).
        sample_size: How many traded opportunities had exactly this combination.
        win_rate: Fraction of those opportunities with a positive realized return.
        average_return_pct: Mean realized return across those opportunities.
    """

    departments: tuple[str, ...]
    sample_size: int
    win_rate: float
    average_return_pct: float


@dataclass(frozen=True, slots=True)
class DepartmentContribution:
    """One department's measured contribution to traded outcomes.

    Attributes:
        department_name: The department's name.
        total_agreements: How many traded opportunities this department agreed with.
        win_contribution_rate: Of all winning traded opportunities, the
            fraction this department agreed with -- "how often was this
            department part of the winning consensus." 0.0 if there were
            no wins.
        loss_contribution_rate: The same, for losing traded opportunities.
    """

    department_name: str
    total_agreements: int
    win_contribution_rate: float
    loss_contribution_rate: float


@dataclass(frozen=True, slots=True)
class WalkForwardStatistics:
    """The full statistical summary of one walk-forward validation run.

    Attributes:
        total_opportunities: Every decision step recorded, traded or not.
        actionable_opportunities: Steps where Chief AI's state was BUY/SELL.
        traded_opportunities: Actionable steps with a forward-simulated outcome.
        win_rate: Fraction of `traded_opportunities` with a positive realized return.
        average_return_pct: Mean realized return across `traded_opportunities`.
        combo_statistics: Outcome broken down by which departments agreed,
            most frequent combination first.
        department_contributions: Every department's own measured
            contribution to wins/losses, alphabetical.
    """

    total_opportunities: int
    actionable_opportunities: int
    traded_opportunities: int
    win_rate: float
    average_return_pct: float
    combo_statistics: list[DepartmentComboStatistics] = field(default_factory=list)
    department_contributions: list[DepartmentContribution] = field(default_factory=list)


def compute_walk_forward_statistics(
    opportunities: list[WalkForwardOpportunity],
) -> WalkForwardStatistics:
    """Aggregate a walk-forward run into department-combination and per-department statistics.

    Args:
        opportunities: Every recorded `WalkForwardOpportunity` from
            `src.engines.validation_engine.walk_forward.run_chief_ai_walk_forward`.

    Returns:
        A `WalkForwardStatistics` summary. All rates are 0.0 (never a
        fabricated non-zero rate) when there is no evidence to measure
        from.
    """
    traded = [o for o in opportunities if o.realized_return_pct is not None]
    actionable = [o for o in opportunities if o.would_have_traded]
    wins = [o for o in traded if o.realized_return_pct is not None and o.realized_return_pct > 0]
    losses = [o for o in traded if o.realized_return_pct is not None and o.realized_return_pct <= 0]

    combo_groups: dict[tuple[str, ...], list[WalkForwardOpportunity]] = defaultdict(list)
    for opportunity in traded:
        combo_groups[tuple(sorted(opportunity.agreeing_departments))].append(opportunity)

    combo_statistics = [
        DepartmentComboStatistics(
            departments=combo,
            sample_size=len(group),
            win_rate=sum(
                1 for o in group if o.realized_return_pct is not None and o.realized_return_pct > 0
            )
            / len(group),
            average_return_pct=sum(o.realized_return_pct or 0.0 for o in group) / len(group),
        )
        for combo, group in sorted(combo_groups.items(), key=lambda item: -len(item[1]))
    ]

    department_names = sorted({name for o in traded for name in o.agreeing_departments})
    department_contributions = [
        DepartmentContribution(
            department_name=name,
            total_agreements=sum(1 for o in traded if name in o.agreeing_departments),
            win_contribution_rate=(
                sum(1 for o in wins if name in o.agreeing_departments) / len(wins) if wins else 0.0
            ),
            loss_contribution_rate=(
                sum(1 for o in losses if name in o.agreeing_departments) / len(losses)
                if losses
                else 0.0
            ),
        )
        for name in department_names
    ]

    return WalkForwardStatistics(
        total_opportunities=len(opportunities),
        actionable_opportunities=len(actionable),
        traded_opportunities=len(traded),
        win_rate=len(wins) / len(traded) if traded else 0.0,
        average_return_pct=(sum(o.realized_return_pct or 0.0 for o in traded) / len(traded))
        if traded
        else 0.0,
        combo_statistics=combo_statistics,
        department_contributions=department_contributions,
    )
