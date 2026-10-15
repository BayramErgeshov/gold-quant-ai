"""Per-strategy Performance statistics -- Intraday/Scalping/Swing kept fully separate.

Per the "Strategy Performance" production requirement: "Every strategy
maintains completely separate statistics: Win Rate, Profit Factor, Sharpe
Ratio, Average Win, Average Loss, Average Holding Time, Trade Quality,
Average Confidence, Best/Worst Market Regimes, Strategy Ranking." Reuses
`build_performance_report` and `classify_strategy`
(`src.engines.statistics_engine.trade_performance_report`) unmodified --
the only new logic here is partitioning closed trades by strategy before
handing each group to that already-built, already-tested report builder,
plus the two averages (confidence/quality) and the best/worst-regime pick
that report doesn't already surface on its own.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from src.engines.statistics_engine.trade_performance_report import (
    PerformanceReport,
    SegmentedProfit,
    build_performance_report,
    classify_strategy,
)
from src.models.trade import Trade
from src.repositories.trade_repository import TradeRepository

# This research platform is nowhere near this many closed trades; a
# generous cap rather than true unbounded pagination, matching
# `src.interfaces.web.performance_service._MAX_CLOSED_TRADES_FOR_REPORT`.
_MAX_CLOSED_TRADES_FOR_REPORT = 5000
_STRATEGY_NAMES: tuple[str, ...] = ("Intraday", "Scalping", "Swing", "Shakky", "MicroScalping")
# Mirrors `trade_performance_report._UNKNOWN_SEGMENT` -- best/worst regime
# only ever picks among regimes actually recorded, never "unknown".
_UNKNOWN_SEGMENT = "unknown"


@dataclass(frozen=True, slots=True)
class StrategyPerformance:
    """One strategy's completely independent performance statistics.

    Attributes:
        strategy: "Intraday"/"Scalping"/"Swing".
        report: The full Performance Validation Framework report
            (`src.engines.statistics_engine.trade_performance_report.
            PerformanceReport`), computed ONLY from this strategy's own
            closed trades -- Win Rate, Profit Factor, Sharpe Ratio,
            Average Win/Loss, Average Holding Time all live here.
        average_confidence_pct: Mean `Trade.confidence_pct` at signal time
            across this strategy's reviewable trades. None if none recorded.
        average_quality_score: Mean `Trade.quality_score` across this
            strategy's reviewable trades. None if none recorded.
        best_market_regime: The regime this strategy's own
            `report.profit_by_market_regime` breakdown shows the highest
            total realized P&L in. None if no regime was ever recorded.
        worst_market_regime: Same, lowest total realized P&L.
        average_mfe: Mean `Trade.max_favorable_excursion` across this
            strategy's reviewable trades. None if never recorded (trades
            closed before that tracking existed, or a strategy whose
            positions this loop never re-monitors after entry).
        average_mae: Mean `Trade.max_adverse_excursion`, same basis.
    """

    strategy: str
    report: PerformanceReport = field(default_factory=PerformanceReport)
    average_confidence_pct: float | None = None
    average_quality_score: float | None = None
    best_market_regime: str | None = None
    worst_market_regime: str | None = None
    average_mfe: float | None = None
    average_mae: float | None = None


@dataclass(frozen=True, slots=True)
class StrategyRanking:
    """One strategy's rank among all three, by profit factor.

    Attributes:
        strategy: "Intraday"/"Scalping"/"Swing".
        rank: 1 = best. Strategies with zero closed trades are excluded
            entirely (an empty track record is not a rankable one) --
            never a fabricated last-place rank.
        profit_factor: The ranking score itself, surfaced for transparency
            (never a hidden/opaque rank).
    """

    strategy: str
    rank: int
    profit_factor: float


@dataclass(frozen=True, slots=True)
class StrategyPerformanceView:
    """Everything the per-strategy performance page/API needs.

    Attributes:
        strategies: One `StrategyPerformance` per known strategy, in
            `_STRATEGY_NAMES` order -- always all three, even ones with
            zero closed trades (an honest empty report, never omitted).
        ranking: Strategies with at least one closed trade, best-to-worst
            by profit factor.
    """

    strategies: list[StrategyPerformance] = field(default_factory=list)
    ranking: list[StrategyRanking] = field(default_factory=list)


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _best_and_worst_regime(segments: list[SegmentedProfit]) -> tuple[str | None, str | None]:
    known = [segment for segment in segments if segment.segment != _UNKNOWN_SEGMENT]
    if not known:
        return None, None
    best = max(known, key=lambda segment: segment.total_pnl)
    worst = min(known, key=lambda segment: segment.total_pnl)
    return best.segment, worst.segment


def _group_by_strategy(trades: list[Trade]) -> dict[str, list[Trade]]:
    grouped: dict[str, list[Trade]] = {name: [] for name in _STRATEGY_NAMES}
    for trade in trades:
        strategy = classify_strategy(trade.department_votes)
        if strategy in grouped:
            grouped[strategy].append(trade)
        # A trade classified "unknown" (department_votes never recorded --
        # journaled before that field existed) cannot be honestly
        # attributed to any one of the three strategies, so it is
        # excluded from every per-strategy statistic rather than guessed.
    return grouped


def _strategy_performance(strategy: str, trades: list[Trade]) -> StrategyPerformance:
    reviewable = [t for t in trades if t.entry_price is not None and t.exit_price is not None]
    report = build_performance_report(trades)
    best_regime, worst_regime = _best_and_worst_regime(report.profit_by_market_regime)
    return StrategyPerformance(
        strategy=strategy,
        report=report,
        average_confidence_pct=_mean(
            [t.confidence_pct for t in reviewable if t.confidence_pct is not None]
        ),
        average_quality_score=_mean(
            [t.quality_score for t in reviewable if t.quality_score is not None]
        ),
        best_market_regime=best_regime,
        worst_market_regime=worst_regime,
        average_mfe=_mean(
            [t.max_favorable_excursion for t in reviewable if t.max_favorable_excursion is not None]
        ),
        average_mae=_mean(
            [t.max_adverse_excursion for t in reviewable if t.max_adverse_excursion is not None]
        ),
    )


def _rank_strategies(strategies: list[StrategyPerformance]) -> list[StrategyRanking]:
    ranked = sorted(
        (s for s in strategies if s.report.trade_count > 0),
        key=lambda s: (s.report.profit_factor, s.report.trade_count),
        reverse=True,
    )
    return [
        StrategyRanking(strategy=s.strategy, rank=index + 1, profit_factor=s.report.profit_factor)
        for index, s in enumerate(ranked)
    ]


async def get_strategy_performance(session: AsyncSession) -> StrategyPerformanceView:
    """Assemble the current per-strategy Performance view.

    Args:
        session: The active database session.

    Returns:
        A `StrategyPerformanceView` computed entirely from persisted,
        closed `Trade` rows -- never a simulated or fabricated statistic.
    """
    closed_trades = await TradeRepository(session).list_by_status(
        "closed", limit=_MAX_CLOSED_TRADES_FOR_REPORT
    )
    grouped = _group_by_strategy(closed_trades)
    strategies = [_strategy_performance(name, grouped[name]) for name in _STRATEGY_NAMES]
    return StrategyPerformanceView(strategies=strategies, ranking=_rank_strategies(strategies))
