"""Performance Validation Framework: full statistics over the real trade journal.

Per the "Performance Validation Framework" production requirement: every
metric here is computed from actually-closed `Trade` rows -- never
simulated or fabricated. A trade missing the field a given breakdown
needs (e.g. `market_regime`/`confidence_pct` on trades journaled before
those columns existed) is grouped under an honest "unknown" segment
rather than silently dropped or guessed.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from src.engines.learning_engine.trade_review import review_closed_trade
from src.engines.statistics_engine.performance import (
    average_loss_pct,
    average_win_pct,
    calmar_ratio,
    expectancy_pct,
    max_consecutive_losses,
    max_consecutive_wins,
    max_drawdown_pct,
    profit_factor,
    recovery_factor,
    sharpe_ratio,
    sortino_ratio,
    win_rate,
)
from src.engines.statistics_engine.risk_metrics import average_r_multiple
from src.models.trade import Trade

_SCALPING_VOTE_KEY = "scalping_engine"
_SWING_VOTE_KEY = "swing_engine"
_SHAKKY_VOTE_KEY = "shakky_engine"
_MICRO_SCALPING_VOTE_KEY = "micro_scalping_engine"
_UNKNOWN_SEGMENT = "unknown"

# Each independent engine runs on a fixed timeframe by this platform's own
# architecture (`src.services.scheduler.live_loop`), so "Profit by
# Timeframe" and "Profit by Strategy" share the same underlying
# classification rather than needing a second, separately-persisted field.
_STRATEGY_TIMEFRAMES: dict[str, str] = {
    "Intraday": "M15",
    "Scalping": "M1/H1",
    "Swing": "D1/W1",
    "Shakky": "M5",
    "MicroScalping": "M1/M5",
}

# A documented simplification, not exact broker/exchange session times
# (real sessions overlap, e.g. the well-known London/New York overlap) --
# four non-overlapping UTC buckets so every trade gets exactly one label.
_SESSION_BOUNDARIES_UTC: tuple[tuple[str, int, int], ...] = (
    ("asian", 0, 8),
    ("london", 8, 13),
    ("london_ny_overlap", 13, 17),
    ("new_york", 17, 22),
    ("off_hours", 22, 24),
)

_CONFIDENCE_RANGES: tuple[tuple[str, float, float], ...] = (
    ("50-60%", 50.0, 60.0),
    ("60-70%", 60.0, 70.0),
    ("70-80%", 70.0, 80.0),
    ("80-90%", 80.0, 90.0),
    ("90-100%", 90.0, 100.01),
)


@dataclass(frozen=True, slots=True)
class SegmentedProfit:
    """Realized performance for one segment of a breakdown dimension.

    Attributes:
        segment: The segment label (e.g. "Scalping", "bull_trend", "asian").
        trade_count: Number of closed trades in this segment.
        total_pnl: Sum of `realized_pnl` across the segment, in account currency.
        win_rate: Fraction of trades in this segment with a positive return.
    """

    segment: str
    trade_count: int
    total_pnl: float
    win_rate: float


@dataclass(frozen=True, slots=True)
class PerformanceReport:
    """The complete Performance Validation Framework report.

    Attributes:
        trade_count: Number of closed, reviewable trades (both entry and
            exit price recorded) included in this report.
        win_rate: Fraction of trades with a positive return.
        profit_factor: Gross profit / gross loss.
        expectancy_pct: Average return per trade, in percent.
        average_r_multiple: Average realized return as a multiple of risk taken.
        average_win_pct: Average return of winning trades, in percent.
        average_loss_pct: Average loss magnitude of losing trades, in percent.
        max_drawdown_pct: Largest peak-to-trough decline in the return-based
            equity curve, in percent.
        max_drawdown_usd: Largest peak-to-trough decline in the realized
            dollar P&L equity curve.
        sharpe_ratio: Annualized Sharpe ratio over per-trade returns.
        sortino_ratio: Annualized Sortino ratio over per-trade returns.
        calmar_ratio: Annualized return / max drawdown, over the actual
            calendar period the trades span. 0.0 if fewer than two trades.
        recovery_factor: Net dollar profit / max dollar drawdown.
        max_consecutive_wins: Longest streak of consecutive winning trades.
        max_consecutive_losses: Longest streak of consecutive losing trades.
        average_holding_time: Average time between a trade's open and
            close, across trades with both timestamps recorded. None if
            no trade has both.
        profit_by_strategy: Breakdown by which independent engine
            (Intraday/Scalping/Swing) produced each trade, inferred from
            its own `department_votes` snapshot -- "unknown" for trades
            journaled before that snapshot existed.
        profit_by_market_regime: Breakdown by `Trade.market_regime` at
            signal time -- "unknown" if not recorded.
        profit_by_session: Breakdown by trading session (Asian/London/
            London-NY overlap/New York/off-hours), classified from
            `Trade.opened_at`'s UTC hour.
        profit_by_timeframe: Breakdown by the executing engine's own
            fixed timeframe -- mirrors `profit_by_strategy`.
        profit_by_confidence_range: Breakdown by `Trade.confidence_pct`
            at signal time, bucketed into 10-point ranges -- "unknown" if
            not recorded.
    """

    trade_count: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    expectancy_pct: float = 0.0
    average_r_multiple: float = 0.0
    average_win_pct: float = 0.0
    average_loss_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    max_drawdown_usd: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    recovery_factor: float = 0.0
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0
    average_holding_time: timedelta | None = None
    profit_by_strategy: list[SegmentedProfit] = field(default_factory=list)
    profit_by_market_regime: list[SegmentedProfit] = field(default_factory=list)
    profit_by_session: list[SegmentedProfit] = field(default_factory=list)
    profit_by_timeframe: list[SegmentedProfit] = field(default_factory=list)
    profit_by_confidence_range: list[SegmentedProfit] = field(default_factory=list)


def classify_strategy(department_votes: dict[str, object] | None) -> str:
    """Infer which independent engine produced a trade from its own vote snapshot.

    Args:
        department_votes: `Trade.department_votes`, if recorded.

    Returns:
        "Scalping"/"Swing"/"Shakky"/"MicroScalping"/"Intraday", or
        "unknown" if `department_votes` was never recorded (a trade
        journaled before that field existed).
    """
    if not department_votes:
        return _UNKNOWN_SEGMENT
    if _SCALPING_VOTE_KEY in department_votes:
        return "Scalping"
    if _SWING_VOTE_KEY in department_votes:
        return "Swing"
    if _SHAKKY_VOTE_KEY in department_votes:
        return "Shakky"
    if _MICRO_SCALPING_VOTE_KEY in department_votes:
        return "MicroScalping"
    return "Intraday"


def classify_trading_session(timestamp: datetime) -> str:
    """Classify a UTC timestamp into a trading session bucket.

    Args:
        timestamp: The timestamp to classify (converted to UTC if aware;
            treated as already UTC if naive).

    Returns:
        One of `_SESSION_BOUNDARIES_UTC`'s labels.
    """
    aware = timestamp if timestamp.tzinfo is not None else timestamp.replace(tzinfo=UTC)
    hour = aware.astimezone(UTC).hour
    for label, start, end in _SESSION_BOUNDARIES_UTC:
        if start <= hour < end:
            return label
    return _UNKNOWN_SEGMENT  # pragma: no cover - unreachable: buckets cover all 24 hours


def classify_confidence_range(confidence_pct: float | None) -> str:
    """Bucket a confidence percentage into a 10-point range.

    Args:
        confidence_pct: `Trade.confidence_pct` at signal time, if recorded.

    Returns:
        A label like "70-80%", or "unknown" if `confidence_pct` is None
        or falls outside every defined bucket.
    """
    if confidence_pct is None:
        return _UNKNOWN_SEGMENT
    for label, low, high in _CONFIDENCE_RANGES:
        if low <= confidence_pct < high:
            return label
    return _UNKNOWN_SEGMENT


def _build_segments(trades: list[Trade], classify: Callable[[Trade], str]) -> list[SegmentedProfit]:
    groups: dict[str, list[Trade]] = {}
    for trade in trades:
        segment = classify(trade)
        groups.setdefault(segment, []).append(trade)

    segments: list[SegmentedProfit] = []
    for segment, group in sorted(groups.items()):
        returns = [
            review_closed_trade(t).realized_return_pct
            for t in group
            if t.entry_price is not None and t.exit_price is not None
        ]
        segments.append(
            SegmentedProfit(
                segment=segment,
                trade_count=len(group),
                total_pnl=sum(t.realized_pnl or 0.0 for t in group),
                win_rate=win_rate(returns),
            )
        )
    return segments


def build_performance_report(trades: list[Trade]) -> PerformanceReport:
    """Build the complete Performance Validation Framework report.

    Args:
        trades: Closed `Trade` rows to analyze, in any order.

    Returns:
        The `PerformanceReport`. All fields default to 0/empty if `trades`
        has no reviewable (entry+exit price recorded) closed trades.
    """
    reviewable = [t for t in trades if t.entry_price is not None and t.exit_price is not None]
    if not reviewable:
        return PerformanceReport()

    reviews = [(trade, review_closed_trade(trade)) for trade in reviewable]
    returns_pct = [review.realized_return_pct for _, review in reviews]
    risk_pcts = [review.risk_pct for _, review in reviews]
    pnls = [trade.realized_pnl or 0.0 for trade, _ in reviews]

    chronological = sorted(
        reviewable, key=lambda t: t.closed_at or datetime.min.replace(tzinfo=UTC)
    )
    dollar_equity_curve = [0.0]
    cumulative = 0.0
    for trade in chronological:
        cumulative += trade.realized_pnl or 0.0
        dollar_equity_curve.append(cumulative)
    starting_equity = 10_000.0
    pct_equity_curve = [starting_equity]
    pct_cumulative = starting_equity
    for _, review in sorted(
        reviews,
        key=lambda pair: pair[0].closed_at or datetime.min.replace(tzinfo=UTC),
    ):
        pct_cumulative *= 1 + review.realized_return_pct / 100
        pct_equity_curve.append(pct_cumulative)

    dollar_peak = 0.0
    max_drawdown_dollars = 0.0
    for value in dollar_equity_curve:
        dollar_peak = max(dollar_peak, value)
        max_drawdown_dollars = max(max_drawdown_dollars, dollar_peak - value)

    closed_timestamps = [t.closed_at for t in reviewable if t.closed_at is not None]
    days_covered = (
        (max(closed_timestamps) - min(closed_timestamps)).total_seconds() / 86400
        if len(closed_timestamps) >= 2
        else 0.0
    )
    total_return_pct = (pct_equity_curve[-1] / starting_equity - 1) * 100

    holding_times = [
        review.holding_time for _, review in reviews if review.holding_time is not None
    ]
    average_holding_time = (
        sum(holding_times, timedelta()) / len(holding_times) if holding_times else None
    )

    return PerformanceReport(
        trade_count=len(reviewable),
        win_rate=win_rate(returns_pct),
        profit_factor=profit_factor(returns_pct),
        expectancy_pct=expectancy_pct(returns_pct),
        average_r_multiple=average_r_multiple(returns_pct, risk_pcts),
        average_win_pct=average_win_pct(returns_pct),
        average_loss_pct=average_loss_pct(returns_pct),
        max_drawdown_pct=max_drawdown_pct(pct_equity_curve),
        max_drawdown_usd=max_drawdown_dollars,
        sharpe_ratio=sharpe_ratio(returns_pct),
        sortino_ratio=sortino_ratio(returns_pct),
        calmar_ratio=calmar_ratio(
            total_return_pct=total_return_pct,
            max_drawdown_pct=max_drawdown_pct(pct_equity_curve),
            days_covered=days_covered,
        ),
        recovery_factor=recovery_factor(net_profit=sum(pnls), max_drawdown=max_drawdown_dollars),
        max_consecutive_wins=max_consecutive_wins(returns_pct),
        max_consecutive_losses=max_consecutive_losses(returns_pct),
        average_holding_time=average_holding_time,
        profit_by_strategy=_build_segments(
            reviewable, lambda t: classify_strategy(t.department_votes)
        ),
        profit_by_market_regime=_build_segments(
            reviewable, lambda t: t.market_regime or _UNKNOWN_SEGMENT
        ),
        profit_by_session=_build_segments(
            reviewable,
            lambda t: classify_trading_session(t.opened_at) if t.opened_at else _UNKNOWN_SEGMENT,
        ),
        profit_by_timeframe=_build_segments(
            reviewable,
            lambda t: _STRATEGY_TIMEFRAMES.get(
                classify_strategy(t.department_votes), _UNKNOWN_SEGMENT
            ),
        ),
        profit_by_confidence_range=_build_segments(
            reviewable, lambda t: classify_confidence_range(t.confidence_pct)
        ),
    )
