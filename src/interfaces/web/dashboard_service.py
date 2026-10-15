"""Data assembly for the local web UI's main dashboard page.

Per the "Main Dashboard" production requirement (Market Status, Regime,
Strategy, Chief AI Decision, Confidence, Trend, Correlation/News/Order
Flow/Books summaries, Active Departments, System Health, Open Positions,
Pending Signals, Closed Trades, Today's PnL, Win Rate, Profit Factor,
Drawdown, Learning Progress). Every field here is read from durable,
already-persisted data (the trade journal, the latest `SystemLog` scan
snapshot `LiveTradingLoop` records each cycle, the books folder, and the
improvement-proposal queue) -- this module never queries MT5 directly, so
it works as an independent process from the live loop and never invents a
value that hasn't actually been computed.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.notifications.formatting import build_reason_tags_ru_for_direction
from src.engines.book_engine.document_extraction import SUPPORTED_EXTENSIONS
from src.engines.learning_engine.trade_review import review_closed_trade
from src.engines.statistics_engine.micro_scalping_stats import compute_micro_scalping_daily_stats
from src.engines.statistics_engine.performance import profit_factor, win_rate
from src.engines.statistics_engine.trade_performance_report import (
    build_performance_report,
    classify_strategy,
)
from src.models.improvement_proposal import PROPOSAL_STATUSES
from src.models.trade import Trade
from src.repositories.book_repository import BookRepository
from src.repositories.improvement_proposal_repository import ImprovementProposalRepository
from src.repositories.runtime_settings_repository import RuntimeSettingsRepository
from src.repositories.system_log_repository import SystemLogRepository
from src.repositories.trade_repository import TradeRepository
from src.settings import get_settings

_SCAN_SNAPSHOT_SOURCE = "market_scan_snapshot"
_SCALPING_SNAPSHOT_SOURCE = "scalping_scan_snapshot"
_SWING_SNAPSHOT_SOURCE = "swing_scan_snapshot"
_SHAKKY_SNAPSHOT_SOURCE = "shakky_scan_snapshot"
_MICRO_SCALPING_SNAPSHOT_SOURCE = "micro_scalping_scan_snapshot"
_BOOKS_WATCHED_DIRECTORY = Path("books")
_CLOSED_TRADES_FOR_METRICS = 200
_RECENT_CLOSED_TRADES_SHOWN = 10
# A scan snapshot older than this many cycle-intervals looks "stalled"
# rather than merely "the next cycle hasn't landed yet" -- a generous
# multiple of the live loop's own 60s default interval
# (`scripts/run_live_loop.py:_SCAN_INTERVAL_SECONDS`), tolerant of one or
# two slow cycles without crying wolf.
_STALE_SNAPSHOT_THRESHOLD = timedelta(minutes=5)


@dataclass(frozen=True, slots=True)
class OpenPositionView:
    """One open position, as shown on the dashboard.

    Per the "Strategy Explanation" production requirement: every trade
    must display Strategy, Trade Quality, Confidence, Risk Score,
    Expected Holding Time, Expected Scenario, Reasons, positive/negative
    confirmations -- all read from what was already persisted (or
    independently measured) at signal time, never recomputed with
    hindsight the position doesn't actually have yet.

    Attributes:
        strategy: "Intraday"/"Scalping"/"Swing"/"unknown", inferred from
            `department_votes` (`classify_strategy`).
        quality_score: Trade Quality Score (0-100) at signal time.
        confidence_pct: Chief AI's overall confidence (0-100) at signal time.
        risk_score: Trade Quality Engine's risk score (0-100) at signal time.
        expected_holding_time_minutes: This strategy's own historically
            measured average holding time across recent closed trades, in
            minutes -- an honest statistical expectation, never a
            fabricated per-trade forecast. None if this strategy has no
            reviewable closed trades yet.
        expected_scenario: `ScenarioPlan.primary_scenario` at signal time.
        reasons: `ChiefAIDecision.reasons` at signal time.
        positive_confirmations: "✅ {department}" tags -- departments
            whose vote agreed with this trade's direction.
        negative_confirmations: "❌ {department}" tags -- departments
            whose vote opposed it (present but didn't block the trade).
        similarity_summary: Per the "Trade Similarity Engine" production
            requirement, a short Russian summary of this trade's own
            historical-analogue search, e.g. "Найдено: 42, прибыльных:
            28, провал: 14, RR 2.1". None for engines that don't compute
            one (Shakky) or trades journaled before this field existed.
    """

    trade_id: str
    direction: str
    entry_price: float | None
    stop_loss: float
    volume: float
    opened_at: datetime | None
    strategy: str = "unknown"
    quality_score: float | None = None
    confidence_pct: float | None = None
    risk_score: float | None = None
    expected_holding_time_minutes: float | None = None
    expected_scenario: str | None = None
    reasons: list[str] = field(default_factory=list)
    positive_confirmations: list[str] = field(default_factory=list)
    negative_confirmations: list[str] = field(default_factory=list)
    similarity_summary: str | None = None


@dataclass(frozen=True, slots=True)
class ClosedTradeView:
    """One closed trade, as shown on the dashboard's recent-history list.

    See `OpenPositionView` for the shared "Strategy Explanation" fields.

    Attributes:
        would_repeat: The "Post Trade Learning" verdict
            (`Trade.post_mortem["would_repeat"]`), if a post-mortem has
            run for this trade. None if not yet reviewed.
    """

    trade_id: str
    direction: str
    realized_pnl: float | None
    closed_at: datetime | None
    strategy: str = "unknown"
    quality_score: float | None = None
    confidence_pct: float | None = None
    risk_score: float | None = None
    expected_holding_time_minutes: float | None = None
    expected_scenario: str | None = None
    reasons: list[str] = field(default_factory=list)
    positive_confirmations: list[str] = field(default_factory=list)
    negative_confirmations: list[str] = field(default_factory=list)
    similarity_summary: str | None = None
    would_repeat: bool | None = None


@dataclass(frozen=True, slots=True)
class BooksSummaryView:
    """Books Engine processing progress.

    Attributes:
        processed: Books already ingested (rows in the `books` table).
        discovered: Supported files currently sitting in the watched
            folder, whether processed yet or not.
    """

    processed: int
    discovered: int


@dataclass(frozen=True, slots=True)
class LearningProgressView:
    """Self-improvement proposal queue counts (validated/rejected hypotheses)."""

    pending: int
    approved: int
    rejected: int


@dataclass(frozen=True, slots=True)
class StrategyStatusView:
    """One independent strategy's own current status, for its dashboard card.

    Per the "User Interface" production requirement: every strategy shows
    its own Searching/Waiting/Trade Found/Trade Open/No Trade status,
    Trade Quality, Confidence and reasoning independently of the other two.

    Attributes:
        status: One of "waiting" (disabled or the loop is paused),
            "searching" (enabled, no cycle recorded yet), "trade_open"
            (this strategy currently has its own open position),
            "trade_found" (last cycle's decision was actionable),
            "no_trade" (last cycle recorded a specific reason it did not trade).
        quality_score: This strategy's own latest Trade Quality Score
            (0-100), if any cycle has run yet.
        confidence_pct: This strategy's own latest measured confidence,
            in [0.0, 100.0].
        reasons: Why this strategy did not trade last cycle, in Russian
            (empty when `status` is "trade_open"/"trade_found"/"waiting"/"searching").
        enabled: Whether this strategy is currently enabled
            (`RuntimeSettings.*_enabled`).
        trades_per_day: Micro Scalping-only "Daily Statistics" figure
            (`src.engines.statistics_engine.micro_scalping_stats`). None
            for every other strategy -- a high-frequency-specific metric,
            not fabricated for slower strategies.
        today_total_profit_usd: Same, today's running realized profit.
        best_trading_hour_utc: Same, the historically most profitable UTC hour.
        worst_trading_hour_utc: Same, the historically least profitable UTC hour.
    """

    status: str
    quality_score: float | None = None
    confidence_pct: float | None = None
    reasons: list[str] = field(default_factory=list)
    enabled: bool = True
    trades_per_day: float | None = None
    today_total_profit_usd: float | None = None
    best_trading_hour_utc: int | None = None
    worst_trading_hour_utc: int | None = None


@dataclass(frozen=True, slots=True)
class DashboardStatus:
    """Everything the main dashboard page needs.

    Attributes:
        market: Symbol name, e.g. "XAUUSD".
        state: The latest cycle's Chief AI decision state, if any scan
            has run yet this process's lifetime.
        confidence_pct: The latest cycle's confidence, if known.
        market_regime: The latest cycle's classified regime, if known.
        ai_explanation: The latest cycle's explanation summary, if known.
        active_strategy: The configured strategy name.
        current_trend: The Trend Agent's own bias this cycle
            ("bullish"/"bearish"/"neutral"), independent of Chief AI's
            overall decision -- None if no technical vote was present yet.
        correlation_summary: The Market Correlation Engine's own vote
            summary this cycle, if that department was present.
        news_summary: The News Intelligence department's own vote summary
            this cycle, if that department was present (this platform's
            reduced mode has no configured news provider, so this is
            usually "not configured" rather than fabricated).
        order_flow_summary: The Order Flow Engine's own vote summary this
            cycle, if that department was present.
        active_departments: Every department that voted this cycle.
        system_health: "healthy" if the latest scan snapshot is recent
            enough that the live loop is clearly still running, "stalled"
            if it has gone quiet, "unknown" if no snapshot exists yet.
        open_positions: Every currently open journaled position.
        pending_signals: Trades still in `status == "pending"` -- ordinarily
            zero; a nonzero count means an order is stuck mid-execution.
        closed_trades: The most recent closed trades, newest first.
        today_pnl: Sum of `realized_pnl` for trades closed today (UTC).
        win_rate_pct: Win rate over the last `_CLOSED_TRADES_FOR_METRICS`
            closed trades, in percent. None if there is no closed trade yet.
        profit_factor: Gross profit / gross loss over the same window.
            None if there is no closed trade yet.
        current_drawdown_usd: Dollar amount the cumulative realized P&L
            over the same window currently sits below its running peak
            (0.0 at a new equity high). Deliberately a dollar figure, not
            a percentage: computing a true percentage drawdown needs the
            account's starting balance, which this MT5-free process does
            not have -- never a fabricated percentage.
        books_summary: Books Engine processing progress.
        learning_progress: Improvement-proposal queue counts.
        last_updated: When the latest scan snapshot was recorded, if any.
        trade_quality_score: The latest cycle's Trade Quality Engine score
            (`src.engines.chief_ai.trade_quality`), 0-100, if any scan has
            run yet.
        risk_score: The latest cycle's Trade Quality Engine risk score,
            0-100, if any scan has run yet.
        mt5_status: "connected"/"disconnected" per the live loop's own
            real connectivity check that same cycle, or "unknown" if no
            scan has run yet -- this web process never queries MT5 itself.
        telegram_configured: Whether a Telegram bot token is set (read-only).
        news_configured: Whether a NewsAPI key is set (read-only).
        no_trade_reasons: Per the "No Trade Explanation" production
            requirement: short Russian reasons Chief AI did not trade
            this cycle, shown alongside `trade_quality_score`/
            `confidence_pct` -- empty unless `state == "WAIT"`.
        next_scan_minutes: Minutes until the next scheduled market scan,
            if a scan has run yet this process's lifetime.
        strategies: Every independent strategy's own current status,
            keyed by "intraday"/"scalping"/"swing".
        technical_sub_signals: Per the "Complete Strategy Builder"
            production requirement: "Show all internal confirmations
            inside every module" -- each Technical Department agent's own
            ✅/❌ evidence tags, keyed by agent name (e.g. "trend",
            "momentum", "smart_money"). Empty until the primary engine's
            first scan this process's lifetime.
        trades_opened_this_week: Count of trades opened in the trailing
            7 days (UTC) across every strategy -- the user's own stated
            target is "3-5 quality trades per week, never less than 1."
        wins_this_week: Closed trades from the trailing 7 days with a
            positive `realized_pnl`.
        losses_this_week: Closed trades from the trailing 7 days with a
            non-positive `realized_pnl`.
    """

    market: str
    state: str | None = None
    confidence_pct: float | None = None
    market_regime: str | None = None
    ai_explanation: str | None = None
    active_strategy: str | None = None
    current_trend: str | None = None
    correlation_summary: str | None = None
    news_summary: str | None = None
    order_flow_summary: str | None = None
    active_departments: list[str] = field(default_factory=list)
    system_health: str = "unknown"
    open_positions: list[OpenPositionView] = field(default_factory=list)
    pending_signals: int = 0
    closed_trades: list[ClosedTradeView] = field(default_factory=list)
    today_pnl: float = 0.0
    win_rate_pct: float | None = None
    profit_factor: float | None = None
    current_drawdown_usd: float = 0.0
    books_summary: BooksSummaryView = field(
        default_factory=lambda: BooksSummaryView(processed=0, discovered=0)
    )
    learning_progress: LearningProgressView = field(
        default_factory=lambda: LearningProgressView(pending=0, approved=0, rejected=0)
    )
    last_updated: datetime | None = None
    trade_quality_score: float | None = None
    risk_score: float | None = None
    mt5_status: str = "unknown"
    telegram_configured: bool = False
    news_configured: bool = False
    no_trade_reasons: list[str] = field(default_factory=list)
    next_scan_minutes: float | None = None
    strategies: dict[str, StrategyStatusView] = field(default_factory=dict)
    technical_sub_signals: dict[str, list[str]] = field(default_factory=dict)
    trades_opened_this_week: int = 0
    wins_this_week: int = 0
    losses_this_week: int = 0


def _department_summary(vote: dict[str, float | str] | None) -> str | None:
    """Summarize one department's snapshot vote for the dashboard.

    Args:
        vote: `{"bias": ..., "confidence": ...}`, or None if that
            department was not present this cycle.

    Returns:
        e.g. "bullish (72% confidence)", or None if `vote` is None --
        never a fabricated summary for an absent department.
    """
    if vote is None:
        return None
    confidence_pct = float(vote.get("confidence", 0.0)) * 100
    return f"{vote.get('bias', 'unknown')} ({confidence_pct:.0f}% confidence)"


def _system_health(last_updated: datetime | None) -> str:
    if last_updated is None:
        return "unknown"
    # Some drivers (e.g. the SQLite backend used by this platform's own
    # faster unit tests) return naive datetimes even for a `DateTime
    # (timezone=True)` column; every timestamp in this platform is UTC
    # internally, so a naive value is always treated as UTC rather than
    # raising on the subtraction below.
    aware_last_updated = (
        last_updated if last_updated.tzinfo is not None else last_updated.replace(tzinfo=UTC)
    )
    age = datetime.now(UTC) - aware_last_updated
    return "healthy" if age <= _STALE_SNAPSHOT_THRESHOLD else "stalled"


def _strategy_owning_open_trade(trade: Trade) -> str:
    """Identify which independent strategy an open trade belongs to.

    Per this platform's own convention: Scalping/Swing/Shakky each journal
    their signal with a single-department vote snapshot keyed only by
    "scalping_engine"/"swing_engine"/"shakky_engine"
    (`_scalping_decision`/`_swing_decision` build the first two;
    `_execute_shakky_trade` builds the third directly, in
    `src.services.scheduler.live_loop`), while the primary (Intraday)
    engine's snapshot always includes "technical" plus other departments
    -- reusing this existing distinction rather than needing to recompute
    a magic number cross-process.
    """
    votes = trade.department_votes or {}
    if "scalping_engine" in votes:
        return "scalping"
    if "swing_engine" in votes:
        return "swing"
    if "shakky_engine" in votes:
        return "shakky"
    if "micro_scalping_engine" in votes:
        return "micro_scalping"
    return "intraday"


def _expected_holding_time_minutes_by_strategy(closed_trades: list[Trade]) -> dict[str, float]:
    """Each strategy's own historically measured average holding time, in minutes.

    Per the "Strategy Explanation" production requirement's "Expected
    Holding Time": an honest statistical expectation drawn from this
    strategy's own recent closed trades (`build_performance_report`,
    already computed for `src.interfaces.web.strategy_performance_service`),
    never a fabricated per-trade forecast.
    """
    groups: dict[str, list[Trade]] = {}
    for trade in closed_trades:
        groups.setdefault(classify_strategy(trade.department_votes), []).append(trade)
    result: dict[str, float] = {}
    for strategy, trades in groups.items():
        holding_time = build_performance_report(trades).average_holding_time
        if holding_time is not None:
            result[strategy] = holding_time.total_seconds() / 60
    return result


def _positive_negative_confirmations(trade: Trade) -> tuple[list[str], list[str]]:
    """Split `build_reason_tags_ru_for_direction`'s tags into ✅/❌ lists.

    Reuses the exact same tags the entry Telegram message already shows
    (`src.core.notifications.formatting`) rather than recomputing
    department agreement a second way.
    """
    if not trade.department_votes:
        return [], []
    direction: Literal["BUY", "SELL"] = "BUY" if trade.direction == "buy" else "SELL"
    tags = build_reason_tags_ru_for_direction(trade.department_votes, direction)
    positive = [tag for tag in tags if tag.startswith("✅")]
    negative = [tag for tag in tags if tag.startswith("❌")]
    return positive, negative


def _format_similarity_summary_ru(data: dict[str, object] | None) -> str | None:
    """Render `Trade.similarity_summary` (a serialized `SimilarityDisplayStats`) in Russian.

    Per the "Trade Similarity Engine" production requirement: "Display
    this information before every trade." None when the trade never had
    one (Shakky, or journaled before this field existed) or found zero
    analogues -- never a fabricated summary.
    """
    if not data or not data.get("found_count"):
        return None
    parts = [
        f"Найдено: {data['found_count']}",
        f"прибыльных: {data['profitable_count']}",
        f"провал: {data['failed_count']}",
    ]
    average_rr = data.get("average_rr")
    if isinstance(average_rr, int | float):
        parts.append(f"RR {average_rr:.1f}")
    return ", ".join(parts)


@dataclass(frozen=True, slots=True)
class _TradeExplanation:
    """Fields shared by `OpenPositionView` and `ClosedTradeView` (see their own docstrings)."""

    strategy: str
    quality_score: float | None
    confidence_pct: float | None
    risk_score: float | None
    expected_holding_time_minutes: float | None
    expected_scenario: str | None
    reasons: list[str]
    positive_confirmations: list[str]
    negative_confirmations: list[str]
    similarity_summary: str | None


def _trade_explanation(
    trade: Trade, expected_holding_time_by_strategy: dict[str, float]
) -> _TradeExplanation:
    strategy = classify_strategy(trade.department_votes)
    positive, negative = _positive_negative_confirmations(trade)
    return _TradeExplanation(
        strategy=strategy,
        quality_score=trade.quality_score,
        confidence_pct=trade.confidence_pct,
        risk_score=trade.risk_score,
        expected_holding_time_minutes=expected_holding_time_by_strategy.get(strategy),
        expected_scenario=(trade.scenario_plan or {}).get("primary_scenario"),
        reasons=trade.reasons or [],
        positive_confirmations=positive,
        negative_confirmations=negative,
        similarity_summary=_format_similarity_summary_ru(trade.similarity_summary),
    )


async def _strategy_status(
    session: AsyncSession,
    *,
    source: str,
    enabled: bool,
    paused: bool,
    has_open_position: bool,
) -> StrategyStatusView:
    """Assemble one strategy's own current status for its dashboard card.

    Args:
        session: The active database session.
        source: This strategy's own `SystemLog.source` snapshot key.
        enabled: `RuntimeSettings.*_enabled` for this strategy.
        paused: `RuntimeSettings.paused` (the global Live Control pause).
        has_open_position: Whether this strategy currently has its own open trade.
    """
    if not enabled or paused:
        return StrategyStatusView(status="waiting", enabled=enabled)
    if has_open_position:
        return StrategyStatusView(status="trade_open", enabled=enabled)

    snapshots = await SystemLogRepository(session).list_by_source(source, limit=1)
    if not snapshots:
        return StrategyStatusView(status="searching", enabled=enabled)

    context = snapshots[0].context
    state = context.get("state")
    quality_score = context.get("trade_quality_score")
    confidence_pct = context.get("confidence_pct")
    reasons = context.get("reasons") or context.get("no_trade_reasons") or []
    if state in ("BUY", "SELL", "trade_found"):
        return StrategyStatusView(
            status="trade_found",
            quality_score=quality_score,
            confidence_pct=confidence_pct,
            enabled=enabled,
        )
    return StrategyStatusView(
        status="no_trade",
        quality_score=quality_score,
        confidence_pct=confidence_pct,
        reasons=list(reasons),
        enabled=enabled,
    )


def _current_drawdown_usd(realized_pnls_chronological: list[float]) -> float:
    """Dollar amount cumulative realized P&L currently sits below its peak."""
    cumulative = 0.0
    peak = 0.0
    for pnl in realized_pnls_chronological:
        cumulative += pnl
        peak = max(peak, cumulative)
    return peak - cumulative


def _count_discovered_books(watched_directory: Path) -> int:
    if not watched_directory.is_dir():
        return 0
    return sum(
        1
        for path in watched_directory.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    )


async def get_dashboard_status(session: AsyncSession) -> DashboardStatus:
    """Assemble the current dashboard status from persisted data.

    Args:
        session: The active database session.

    Returns:
        The `DashboardStatus` for the main page.
    """
    snapshots = await SystemLogRepository(session).list_by_source(_SCAN_SNAPSHOT_SOURCE, limit=1)
    latest = snapshots[0] if snapshots else None
    context = latest.context if latest is not None else {}
    department_votes: dict[str, dict[str, float | str]] = context.get("department_votes") or {}

    trade_repository = TradeRepository(session)
    closed_trades = await trade_repository.list_by_status(
        "closed", limit=_CLOSED_TRADES_FOR_METRICS
    )
    expected_holding_time_by_strategy = _expected_holding_time_minutes_by_strategy(closed_trades)

    open_trades = await trade_repository.list_open()

    def _opened_within_last_week(trade: Trade, *, cutoff: datetime) -> bool:
        if trade.opened_at is None:
            return False
        opened_at = (
            trade.opened_at
            if trade.opened_at.tzinfo is not None
            else trade.opened_at.replace(tzinfo=UTC)
        )
        return opened_at >= cutoff

    week_ago = datetime.now(UTC) - timedelta(days=7)
    trades_opened_this_week = sum(
        1
        for trade in (*closed_trades, *open_trades)
        if _opened_within_last_week(trade, cutoff=week_ago)
    )
    wins_this_week = sum(
        1
        for trade in closed_trades
        if _opened_within_last_week(trade, cutoff=week_ago) and (trade.realized_pnl or 0.0) > 0
    )
    losses_this_week = sum(
        1
        for trade in closed_trades
        if _opened_within_last_week(trade, cutoff=week_ago) and (trade.realized_pnl or 0.0) <= 0
    )
    open_positions = []
    for trade in open_trades:
        explanation = _trade_explanation(trade, expected_holding_time_by_strategy)
        open_positions.append(
            OpenPositionView(
                trade_id=str(trade.id),
                direction=trade.direction,
                entry_price=trade.entry_price,
                stop_loss=trade.stop_loss,
                volume=trade.volume,
                opened_at=trade.opened_at,
                strategy=explanation.strategy,
                quality_score=explanation.quality_score,
                confidence_pct=explanation.confidence_pct,
                risk_score=explanation.risk_score,
                expected_holding_time_minutes=explanation.expected_holding_time_minutes,
                expected_scenario=explanation.expected_scenario,
                reasons=explanation.reasons,
                positive_confirmations=explanation.positive_confirmations,
                negative_confirmations=explanation.negative_confirmations,
                similarity_summary=explanation.similarity_summary,
            )
        )
    open_strategy_names = {_strategy_owning_open_trade(trade) for trade in open_trades}
    pending_signals = len(await trade_repository.list_by_status("pending", limit=100))

    today = datetime.now(UTC).date()
    today_pnl = sum(
        trade.realized_pnl or 0.0
        for trade in closed_trades
        if trade.closed_at is not None and trade.closed_at.date() == today
    )
    closed_trade_views = []
    for trade in closed_trades[:_RECENT_CLOSED_TRADES_SHOWN]:
        explanation = _trade_explanation(trade, expected_holding_time_by_strategy)
        closed_trade_views.append(
            ClosedTradeView(
                trade_id=str(trade.id),
                direction=trade.direction,
                realized_pnl=trade.realized_pnl,
                closed_at=trade.closed_at,
                would_repeat=(trade.post_mortem or {}).get("would_repeat"),
                strategy=explanation.strategy,
                quality_score=explanation.quality_score,
                confidence_pct=explanation.confidence_pct,
                risk_score=explanation.risk_score,
                expected_holding_time_minutes=explanation.expected_holding_time_minutes,
                expected_scenario=explanation.expected_scenario,
                reasons=explanation.reasons,
                positive_confirmations=explanation.positive_confirmations,
                negative_confirmations=explanation.negative_confirmations,
                similarity_summary=explanation.similarity_summary,
            )
        )

    reviewable_trades = [
        trade
        for trade in closed_trades
        if trade.entry_price is not None and trade.exit_price is not None
    ]
    returns_pct = [review_closed_trade(trade).realized_return_pct for trade in reviewable_trades]
    win_rate_pct = win_rate(returns_pct) * 100 if returns_pct else None
    profit_factor_value = profit_factor(returns_pct) if returns_pct else None
    # `list_by_status` orders by `created_at` (when the trade was first
    # journaled, i.e. opened) -- the equity curve needs actual closing
    # order, which for trades with overlapping open times is not always
    # the same thing, so sort by `closed_at` explicitly rather than just
    # reversing the query's own order.
    chronologically_closed = sorted(
        closed_trades, key=lambda trade: trade.closed_at or datetime.min.replace(tzinfo=UTC)
    )
    chronological_pnls = [trade.realized_pnl or 0.0 for trade in chronologically_closed]
    drawdown_usd = _current_drawdown_usd(chronological_pnls)

    proposals = await ImprovementProposalRepository(session).list_all(limit=500)
    proposal_counts = dict.fromkeys(PROPOSAL_STATUSES, 0)
    for proposal in proposals:
        proposal_counts[proposal.status] = proposal_counts.get(proposal.status, 0) + 1
    learning_progress = LearningProgressView(
        pending=proposal_counts.get("pending", 0),
        approved=proposal_counts.get("approved", 0),
        rejected=proposal_counts.get("rejected", 0),
    )

    books_summary = BooksSummaryView(
        processed=len(await BookRepository(session).list_all(limit=1000)),
        discovered=_count_discovered_books(_BOOKS_WATCHED_DIRECTORY),
    )

    market = str(context.get("market")) if context.get("market") else "XAUUSD"
    last_updated = latest.created_at if latest is not None else None

    mt5_connected = context.get("mt5_connected")
    if mt5_connected is None:
        mt5_status = "unknown"
    else:
        mt5_status = "connected" if mt5_connected else "disconnected"

    data_providers = get_settings().data_providers
    telegram_configured = bool(get_settings().telegram_env.bot_token.get_secret_value())
    news_configured = bool(data_providers.newsapi_api_key.get_secret_value())

    runtime_settings = await RuntimeSettingsRepository(session).get_or_create_default()
    strategies = {
        "intraday": await _strategy_status(
            session,
            source=_SCAN_SNAPSHOT_SOURCE,
            enabled=runtime_settings.intraday_enabled,
            paused=runtime_settings.paused,
            has_open_position="intraday" in open_strategy_names,
        ),
        "scalping": await _strategy_status(
            session,
            source=_SCALPING_SNAPSHOT_SOURCE,
            enabled=runtime_settings.scalping_enabled,
            paused=runtime_settings.paused,
            has_open_position="scalping" in open_strategy_names,
        ),
        "swing": await _strategy_status(
            session,
            source=_SWING_SNAPSHOT_SOURCE,
            enabled=runtime_settings.swing_enabled,
            paused=runtime_settings.paused,
            has_open_position="swing" in open_strategy_names,
        ),
        "shakky": await _strategy_status(
            session,
            source=_SHAKKY_SNAPSHOT_SOURCE,
            enabled=runtime_settings.shakky_enabled,
            paused=runtime_settings.paused,
            has_open_position="shakky" in open_strategy_names,
        ),
        "micro_scalping": await _strategy_status(
            session,
            source=_MICRO_SCALPING_SNAPSHOT_SOURCE,
            enabled=runtime_settings.micro_scalping_enabled,
            paused=runtime_settings.paused,
            has_open_position="micro_scalping" in open_strategy_names,
        ),
    }
    micro_scalping_daily_stats = compute_micro_scalping_daily_stats(
        [
            trade
            for trade in closed_trades
            if classify_strategy(trade.department_votes) == "MicroScalping"
        ]
    )
    strategies["micro_scalping"] = replace(
        strategies["micro_scalping"],
        trades_per_day=micro_scalping_daily_stats.trades_per_day,
        today_total_profit_usd=micro_scalping_daily_stats.today_total_profit_usd,
        best_trading_hour_utc=micro_scalping_daily_stats.best_trading_hour_utc,
        worst_trading_hour_utc=micro_scalping_daily_stats.worst_trading_hour_utc,
    )

    return DashboardStatus(
        market=market,
        state=context.get("state"),
        confidence_pct=context.get("confidence_pct"),
        market_regime=context.get("market_regime"),
        ai_explanation=context.get("explanation"),
        active_strategy=context.get("strategy_name"),
        current_trend=context.get("current_trend"),
        correlation_summary=_department_summary(department_votes.get("correlation")),
        news_summary=_department_summary(department_votes.get("news")) or "не настроено",
        order_flow_summary=_department_summary(department_votes.get("order_flow")),
        active_departments=sorted(department_votes),
        system_health=_system_health(last_updated),
        open_positions=open_positions,
        pending_signals=pending_signals,
        closed_trades=closed_trade_views,
        today_pnl=today_pnl,
        win_rate_pct=win_rate_pct,
        profit_factor=profit_factor_value,
        current_drawdown_usd=drawdown_usd,
        books_summary=books_summary,
        learning_progress=learning_progress,
        last_updated=last_updated,
        trade_quality_score=context.get("trade_quality_score"),
        risk_score=context.get("risk_score"),
        mt5_status=mt5_status,
        telegram_configured=telegram_configured,
        news_configured=news_configured,
        no_trade_reasons=context.get("no_trade_reasons") or [],
        next_scan_minutes=context.get("next_scan_minutes"),
        technical_sub_signals=context.get("sub_signals") or {},
        strategies=strategies,
        trades_opened_this_week=trades_opened_this_week,
        wins_this_week=wins_this_week,
        losses_this_week=losses_this_week,
    )
