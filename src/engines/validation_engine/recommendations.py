"""Turn walk-forward statistics into reviewable improvement proposals.

Per the "Historical Walk-Forward Validation" production requirement: "Use
ONLY to generate improvement recommendations -- never automatically
change strategy." Reuses the existing `Hypothesis`/`ImprovementProposal`
pipeline (`src.engines.learning_engine.hypothesis`,
`src.engines.learning_engine.proposal`) already built for Post-Trade
Learning -- every proposal this module builds starts `status="pending"`
and requires the same explicit user review before anything downstream
acts on it.
"""

from __future__ import annotations

from src.engines.learning_engine.hypothesis import Hypothesis
from src.engines.learning_engine.proposal import build_proposal_from_hypothesis
from src.engines.validation_engine.statistics import (
    DepartmentComboStatistics,
    WalkForwardStatistics,
)
from src.models.improvement_proposal import ImprovementProposal

# Below this many traded opportunities, a combination's win rate is not
# yet statistically meaningful enough to propose acting on.
_MIN_SAMPLE_SIZE_FOR_RECOMMENDATION = 20
_STRONG_WIN_RATE = 0.6
_WEAK_WIN_RATE = 0.4
_HIGH_PRIORITY_WIN_RATE = 0.7
_HIGH_PRIORITY_LOSS_WIN_RATE = 0.3


def generate_recommendations(
    statistics: WalkForwardStatistics, *, symbol_name: str, timeframe: str
) -> list[ImprovementProposal]:
    """Build pending `ImprovementProposal` rows from a walk-forward run's statistics.

    Args:
        statistics: The aggregated `WalkForwardStatistics`.
        symbol_name: The instrument this validation ran over, for the
            proposal's own title/context.
        timeframe: The decision timeframe this validation ran over.

    Returns:
        One proposal per statistically meaningful combination (win rate
        clearly strong or clearly weak, with enough sample size) --
        never one for combinations too thin to say anything about, and
        never applied automatically; each starts `status="pending"`.
    """
    proposals: list[ImprovementProposal] = []
    for combo in statistics.combo_statistics:
        if combo.sample_size < _MIN_SAMPLE_SIZE_FOR_RECOMMENDATION:
            continue
        if combo.win_rate >= _STRONG_WIN_RATE:
            proposals.append(_strong_combo_proposal(combo, symbol_name, timeframe))
        elif combo.win_rate <= _WEAK_WIN_RATE:
            proposals.append(_weak_combo_proposal(combo, symbol_name, timeframe))
    return proposals


def _combo_label(departments: tuple[str, ...]) -> str:
    return ", ".join(departments) if departments else "no agreeing department"


def _historical_statistics(combo: DepartmentComboStatistics) -> dict[str, float]:
    return {
        "win_rate": combo.win_rate,
        "average_return_pct": combo.average_return_pct,
        "sample_size": float(combo.sample_size),
    }


def _strong_combo_proposal(
    combo: DepartmentComboStatistics, symbol_name: str, timeframe: str
) -> ImprovementProposal:
    label = _combo_label(combo.departments)
    hypothesis = Hypothesis(
        question=(
            f"Should the combination [{label}] be weighted higher for {symbol_name} {timeframe}?"
        ),
        motivation=(
            f"Walk-forward validation found {combo.sample_size} historical opportunities "
            f"where exactly this combination of departments agreed, with a "
            f"{combo.win_rate:.0%} win rate."
        ),
        supporting_evidence=(
            f"Average return {combo.average_return_pct:+.2f}% across "
            f"{combo.sample_size} simulated opportunities."
        ),
        expected_outcome="Higher realized win rate when this specific combination recurs live.",
        validation_plan=(
            "Re-run this walk-forward validation on the next 1-2 years of new data before "
            "applying any weight change."
        ),
        success_criteria=f"Win rate stays at or above {_STRONG_WIN_RATE:.0%} out-of-sample.",
        failure_criteria=f"Win rate falls below {_WEAK_WIN_RATE:.0%} out-of-sample.",
        priority="P1" if combo.win_rate >= _HIGH_PRIORITY_WIN_RATE else "P2",
    )
    return build_proposal_from_hypothesis(
        hypothesis,
        historical_statistics=_historical_statistics(combo),
        validation_results={"sample_size": float(combo.sample_size)},
        potential_risk=(
            "Overfitting to this specific historical period -- the combination may not "
            "repeat with the same edge live."
        ),
    )


def _weak_combo_proposal(
    combo: DepartmentComboStatistics, symbol_name: str, timeframe: str
) -> ImprovementProposal:
    label = _combo_label(combo.departments)
    hypothesis = Hypothesis(
        question=(
            f"Should the combination [{label}] be weighted lower (or excluded) for "
            f"{symbol_name} {timeframe}?"
        ),
        motivation=(
            f"Walk-forward validation found {combo.sample_size} historical opportunities "
            f"where exactly this combination of departments agreed, with only a "
            f"{combo.win_rate:.0%} win rate."
        ),
        supporting_evidence=(
            f"Average return {combo.average_return_pct:+.2f}% across "
            f"{combo.sample_size} simulated opportunities."
        ),
        expected_outcome="Fewer low-quality trades when this specific combination recurs live.",
        validation_plan=(
            "Re-run this walk-forward validation on the next 1-2 years of new data before "
            "applying any weight change."
        ),
        success_criteria=(
            f"Win rate stays at or below {_WEAK_WIN_RATE:.0%} out-of-sample "
            "(confirms de-weighting was justified)."
        ),
        failure_criteria=(
            f"Win rate rises above {_STRONG_WIN_RATE:.0%} out-of-sample "
            "(this cycle's weakness was not persistent)."
        ),
        priority="P1" if combo.win_rate <= _HIGH_PRIORITY_LOSS_WIN_RATE else "P2",
    )
    return build_proposal_from_hypothesis(
        hypothesis,
        historical_statistics=_historical_statistics(combo),
        validation_results={"sample_size": float(combo.sample_size)},
        potential_risk=(
            "This combination may recur with better results live -- de-weighting could "
            "suppress genuinely good future setups."
        ),
    )
