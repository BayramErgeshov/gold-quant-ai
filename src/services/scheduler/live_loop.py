"""Live trading loop (Phase 20 "Live Loop").

Ties the Market Update Workflow (`src.workflows.market_update.pipeline`),
the Signal Workflow (`src.workflows.trade.pipeline`) and the Trade
Monitoring Workflow (`src.workflows.execution.position_monitor`) into one
continuously running asyncio loop: check open positions for break-even,
scan the market, and act on the resulting decision if it is actionable —
every cycle in its own database session, per CODING_STANDARDS.md
("Repositories accept an `AsyncSession` via constructor injection").

Demo-account-only per this platform's explicit operating instructions:
`MarketScanConfig.live_trading_approved` must stay False unless the user
has separately and explicitly approved live trading (FAILSAFE_PROTOCOL.md).

Per the "Multi Strategy"/"Parallel Strategy Execution" production
requirement: "Run all strategies simultaneously: Scalping, Intraday,
Swing. Chief AI must decide independently for every opportunity... Never
block one strategy because another strategy already has an active
trade." The independent Scalping Engine
(`src.engines.scalping_engine.service`, Phase 22) and Swing Engine
(`src.engines.swing_engine.service`, Phase 26) are both wired in the same
optional, opt-in way as Correlation/Order Flow (Phase 21): pass
`scalping_service=`/`swing_service=` to enable each. Every enabled engine
is evaluated independently each cycle and executed if it qualifies on its
own evidence. Each strategy is limited to exactly one of its OWN open
positions (`_strategy_has_open_position`, keyed by that engine's own
distinct magic number) -- one strategy's open trade never blocks
another's. On top of that per-strategy limit, every engine (not just
Intraday) evaluates the PORTFOLIO's combined exposure across all open
positions from every strategy (`check_exposure_limits`) and the optional
overall position-count ceiling (`_portfolio_position_cap_reached`)
before executing -- both gates apply to every engine equally. This
platform never picks only one style per cycle (a superseded design, per
an earlier revision of this module and
`src.engines.chief_ai.trade_style_router`, now removed).
"""

from __future__ import annotations

import asyncio
import dataclasses
import uuid
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC, date, datetime, timedelta
from typing import Literal, overload

from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.technical.volatility import average_true_range
from src.common.logging import get_logger
from src.core.agents.confluence import CombinedVote, grade_from_confidence, vote_bias
from src.core.execution.magic_number import compute_magic_number
from src.core.execution.mt5_client import MT5Client, OpenPosition, OrderRequest
from src.core.execution.order_validation import ExecutionValidationRequest, validate_execution
from src.core.execution.position_reconciliation import reconcile_positions
from src.core.ml.model import ClassificationModel, RegressionModel
from src.core.notifications.formatting import (
    NoTradeMessageData,
    PositionEventData,
    build_no_trade_reasons_ru,
    format_no_trade_message,
    format_position_event_message,
    format_pre_close_report_message,
)
from src.core.notifications.telegram_client import TelegramNotifier
from src.core.technical_analysis.agent import TechnicalAgent
from src.engines.chief_ai.decision import ChiefAIDecision
from src.engines.chief_ai.explanation import explain_decision
from src.engines.chief_ai.strategy_profile import (
    TECHNICAL_AGENT_MODULE_NAMES,
    ModuleSetting,
    apply_profile_to_agents,
    apply_profile_to_department_reliability,
    profile_agent_weights,
)
from src.engines.chief_ai.trade_quality import compute_trade_quality
from src.engines.correlation_engine.analysis import CorrelationAnalysisService
from src.engines.correlation_engine.ingestion import CorrelatedInstrumentIngestionService
from src.engines.historical_engine.mt5_ingestion import MT5HistoricalIngestionService
from src.engines.historical_engine.similarity import (
    SimilarityDisplayStats,
    summarize_matches_for_direction,
)
from src.engines.historical_engine.similarity_service import HistoricalSimilarityService
from src.engines.learning_engine.department_performance import (
    compute_department_reliability_scores,
)
from src.engines.learning_engine.post_mortem import PostMortemService
from src.engines.learning_engine.weight_optimizer import maybe_generate_recommendations
from src.engines.micro_scalping_engine.entry_filters import (
    check_momentum as micro_scalping_check_momentum,
)
from src.engines.micro_scalping_engine.exit_management import MicroScalpingExitDecision
from src.engines.micro_scalping_engine.exit_management import (
    evaluate_exit as evaluate_micro_scalping_exit,
)
from src.engines.micro_scalping_engine.service import (
    MicroScalpingAnalysisOutcome,
    MicroScalpingAnalysisService,
    MicroScalpingSignal,
)
from src.engines.order_flow_engine.service import OrderFlowAnalysisService
from src.engines.risk_engine.dynamic_stop import DynamicStopInputs
from src.engines.risk_engine.exposure import check_exposure_limits
from src.engines.risk_engine.position_sizing import (
    compute_fixed_lot_position_size,
    compute_position_size,
)
from src.engines.risk_engine.session_schedule import (
    SessionSchedule,
    has_pre_close_report_already_run_today,
    is_weekend_approaching,
    is_within_pre_close_window,
)
from src.engines.scalping_engine.position_sizing import (
    ScalpingRiskFactors,
    compute_scalping_risk_pct,
)
from src.engines.scalping_engine.service import (
    ScalpingAnalysisOutcome,
    ScalpingAnalysisService,
    ScalpingSignal,
)
from src.engines.shakky_engine.exit_management import evaluate_exit
from src.engines.shakky_engine.hold_manager import HoldAssessment, assess_hold
from src.engines.shakky_engine.position_scaling import DEFAULT_SCALE_FRACTION, evaluate_scaling
from src.engines.shakky_engine.service import (
    ShakkyAnalysisOutcome,
    ShakkyAnalysisService,
    ShakkySignal,
)
from src.engines.shakky_engine.trend_confidence import (
    TrendConfidenceAssessment,
    assess_trend_confidence,
    bucket_trend_confidence_level,
)
from src.engines.statistics_engine.probability import ProbabilityEstimate
from src.engines.swing_engine.position_sizing import SwingRiskFactors, compute_swing_risk_pct
from src.engines.swing_engine.service import (
    SwingAnalysisOutcome,
    SwingAnalysisService,
    SwingSignal,
)
from src.models.candle import Candle
from src.models.correlated_price import CorrelatedPrice
from src.models.runtime_settings import RuntimeSettings
from src.models.trade import Trade
from src.repositories.book_claim_repository import BookClaimRepository
from src.repositories.candle_repository import CandleRepository
from src.repositories.correlated_instrument_repository import CorrelatedInstrumentRepository
from src.repositories.correlated_price_repository import CorrelatedPriceRepository
from src.repositories.historical_similarity_repository import HistoricalSimilarityRepository
from src.repositories.improvement_proposal_repository import ImprovementProposalRepository
from src.repositories.news_article_repository import NewsArticleRepository
from src.repositories.runtime_settings_repository import RuntimeSettingsRepository
from src.repositories.strategy_profile_repository import StrategyProfileRepository
from src.repositories.system_log_repository import SystemLogRepository
from src.repositories.trade_repository import TradeRepository
from src.repositories.weight_recommendation_repository import DepartmentWeightOverrideRepository
from src.workflows.execution.position_monitor import PositionMonitor
from src.workflows.market_update.pipeline import (
    MarketScanConfig,
    MarketScanner,
    MarketScanResult,
    exposure_state_from_positions,
)
from src.workflows.reporting.pre_close_report import assess_position_before_close
from src.workflows.trade.pipeline import SignalWorkflow, SignalWorkflowInput

logger = get_logger(__name__)

_DEFAULT_BREAKEVEN_TRIGGER_R_MULTIPLE = 1.0
_SCALPING_M1_CANDLE_COUNT = 60
_SCALPING_HTF_TIMEFRAME = "H1"
_SCALPING_HTF_CANDLE_COUNT = 30
_SCALPING_STRATEGY_SUFFIX = "_scalp"
# Per the "Complete Multi-Timeframe Analysis" production requirement's own
# Scalping role ("Primary: H1 + M15. Confirmation: M5. Entry: M5/M1"): M15
# is an additional confirmation layer alongside the existing H1 read, and
# M5 confirms between the higher-timeframe reads and the M1 entry signal.
_SCALPING_M15_CANDLE_COUNT = 60
_SCALPING_M5_CANDLE_COUNT = 60
# 250 D1 bars covers EMA200 (the longest single indicator any technical
# agent computes), matching `scripts/run_live_loop.py`'s own
# `_TECHNICAL_WINDOW_SIZE` rationale for the Intraday engine.
_SWING_D1_CANDLE_COUNT = 250
_SWING_W1_TIMEFRAME = "W1"
_SWING_W1_CANDLE_COUNT = 30
_SWING_STRATEGY_SUFFIX = "_swing"
# Per the "Complete Multi-Timeframe Analysis" production requirement's
# own Swing role ("Primary: D1 + H4. Confirmation: H1. Entry: M15/M5"):
# H4 is an intermediate confirmation layer between the D1 primary read
# and the weekly W1 context; M15 confirms short-term entry timing.
_SWING_H4_CANDLE_COUNT = 60
_SWING_M15_CANDLE_COUNT = 60
# Per the "Trade Similarity Engine" production requirement: "Before
# opening every trade search the historical database." Scalping searches
# its own M1 entry timeframe, Swing its own D1 primary timeframe -- each
# strategy's own analogues, not Intraday's (already computed against
# `MarketScanConfig.timeframe` inside `MarketScanner.scan()`). Same
# horizon as `src.workflows.market_update.pipeline`'s own
# `_SIMILARITY_FORWARD_BARS` (independently defined, not shared, since
# the two modules intentionally don't import each other's private constants).
_SIMILARITY_FORWARD_BARS = 10
_SCALPING_SIMILARITY_TIMEFRAME = "M1"
_SWING_SIMILARITY_TIMEFRAME = "D1"
# Shakky ("Classic M5 Strategy") is primary M5, confirmation M15/H1/H4/D1
# per its own spec -- 80 bars on every confirmation timeframe comfortably
# covers the EMA50 stack used by `_trend_stack_direction` (needs at least
# 50), and 100 on the primary M5 covers `_MIN_M5_CANDLES` with margin.
_SHAKKY_M5_CANDLE_COUNT = 100
_SHAKKY_M15_CANDLE_COUNT = 80
_SHAKKY_H1_CANDLE_COUNT = 80
_SHAKKY_H4_CANDLE_COUNT = 80
_SHAKKY_D1_CANDLE_COUNT = 80
_SHAKKY_DXY_CANDLE_COUNT = 30
_SHAKKY_STRATEGY_SUFFIX = "_shakky"
# Per Shakky's own production requirement: "Minimum lot: 0.01" -- a fixed
# size, never risk-scaled by confidence (which Shakky, being purely
# rule-based, does not even compute).
_SHAKKY_FIXED_LOT_SIZE = 0.01
# Same disclosed ICE US Dollar Index formula weights as
# `src.engines.correlation_engine.analysis._DXY_PROXY_WEIGHTS`, duplicated
# here (not imported) so Shakky's own DXY data path never reaches into
# the Correlation Engine package it must otherwise stay independent of --
# per its own spec's one explicit exception, "Correlation Engine (except DXY)".
_SHAKKY_DXY_PROXY_WEIGHTS: dict[str, float] = {
    "EURUSD": -0.6316,
    "USDJPY": 0.1489,
    "GBPUSD": -0.1303,
    "USDCAD": 0.0997,
    "USDCHF": 0.0395,
}
_SHAKKY_DXY_PROXY_SOURCE = "shakky_dxy_proxy"
# Same MT5 comment-length limit `src.workflows.trade.pipeline` measured
# against a real terminal -- duplicated locally since Shakky bypasses
# `SignalWorkflow` entirely (see `_execute_shakky_trade`).
_SHAKKY_MT5_COMMENT_MAX_LENGTH = 29
# Micro Scalping is primary M1/M5, confirmation M15/H1 only (per its own
# narrower spec -- no H4/D1) -- reuses Shakky's own confirmation logic
# (`src.engines.micro_scalping_engine.service`) with its own additional
# gates (spread/liquidity/momentum/news) and its own dynamic
# profit-target/trailing exit management layered on top.
_MICRO_SCALPING_M1_CANDLE_COUNT = 100
_MICRO_SCALPING_M5_CANDLE_COUNT = 100
_MICRO_SCALPING_M15_CANDLE_COUNT = 80
_MICRO_SCALPING_H1_CANDLE_COUNT = 80
_MICRO_SCALPING_STRATEGY_SUFFIX = "_micro_scalp"
_MICRO_SCALPING_SNAPSHOT_SOURCE = "micro_scalping_scan_snapshot"
_MICRO_SCALPING_HOLD_SNAPSHOT_SOURCE = "micro_scalping_hold_snapshot"
# A reasonable, deliberately small default fixed lot -- the user's own
# spec asks for "Lot Size (Auto or Manual)" in Settings; this is only
# the constructed fallback when the "manual" override is left unset.
_MICRO_SCALPING_DEFAULT_FIXED_LOT_SIZE = 0.05
_MICRO_SCALPING_DEFAULT_MIN_CONFIDENCE = 60.0
# Production incident: this was originally 5.0, an untested guess --
# this account's real XAUUSD spread sits at a stable ~36 points, so
# every cycle was silently rejected at the spread gate and the engine
# never once qualified a trade. 60.0 sits comfortably above that
# observed baseline; also overridable per-cycle via
# `RuntimeSettings.micro_scalping_max_spread_points` so a future shift
# in the account's real spread doesn't require another code change.
_MICRO_SCALPING_DEFAULT_MAX_SPREAD_POINTS = 60.0
_MICRO_SCALPING_DEFAULT_MIN_PROFIT_TARGET_USD = 1.0
_MICRO_SCALPING_DEFAULT_MAX_HOLDING_MINUTES = 30.0
# How many recent high-importance articles to fetch for the "no
# high-impact news" entry gate -- `check_recent_high_impact_news` only
# ever looks at the single most recent one; a small buffer beyond 1
# guards against the very first row being an edge-case duplicate.
_MICRO_SCALPING_NEWS_LOOKBACK_LIMIT = 5
_MICRO_SCALPING_MT5_COMMENT_MAX_LENGTH = 29
# Same ATR period Shakky's own Trend Confidence Engine uses
# (`shakky_engine.trend_confidence._ATR_PERIOD`) -- one shared, already-
# validated volatility window rather than a second, arbitrary one.
_MICRO_SCALPING_ATR_PERIOD = 14
# How many recent bars to top up per cycle for each enabled correlated
# instrument -- matches the primary symbol's own per-cycle top-up count
# (`MarketScanner.scan()`'s `window_size + 50`), enough to keep the
# rolling correlation window current without re-downloading deep history
# every cycle.
_CORRELATED_INSTRUMENT_TOPUP_COUNT = 50
# XAUUSD is quoted with 2 decimal digits by this platform's broker
# (MT5_ENGINE.md "Symbol Specification"); one point is therefore $0.01,
# matching `src.workflows.market_update.pipeline`'s own `_POINT_SIZE`.
_POINT_SIZE = 0.01
# How many recently closed trades to measure department reliability from
# (`src.engines.learning_engine.department_performance`) -- recent enough
# that a department's weight reflects its current behavior, not its
# entire multi-year history.
_RELIABILITY_LOOKBACK_TRADES = 200
# Saturates at 20 accepted book claims -- a round, documented cap rather
# than a fabricated precise number; `books_confluence` is 0.0 (no
# contribution) until Phase 9's claim validation actually accepts claims.
_BOOKS_CONFLUENCE_SATURATION_COUNT = 20
# A WAIT decision recurs almost every cycle -- sending the "No Trade"
# Telegram explanation every cycle would spam the user, so it is sent at
# most this often, as a periodic digest.
_NO_TRADE_TELEGRAM_MIN_INTERVAL = timedelta(minutes=15)

# "Risk Mode" (User Interface production requirement): a real multiplier
# on `risk_per_trade_pct`, not a cosmetic label.
_RISK_MODE_MULTIPLIERS: dict[str, float] = {
    "conservative": 0.5,
    "normal": 1.0,
    "aggressive": 1.5,
}

# "Demo Learning Mode" (production requirement): a bounded discount off
# any explicitly-configured confidence/quality threshold, so more
# borderline setups clear the bar and generate learning data -- capped by
# a floor so this mode never removes the gate entirely, only loosens it.
_DEMO_LEARNING_THRESHOLD_DISCOUNT_PCT = 10.0
_DEMO_LEARNING_MIN_THRESHOLD_PCT = 50.0


@overload
def _demo_learning_discount(threshold_pct: float, runtime_settings: RuntimeSettings) -> float: ...
@overload
def _demo_learning_discount(threshold_pct: None, runtime_settings: RuntimeSettings) -> None: ...
def _demo_learning_discount(
    threshold_pct: float | None, runtime_settings: RuntimeSettings
) -> float | None:
    """Apply "Demo Learning Mode"'s bounded threshold discount, if enabled.

    Only discounts a threshold the user has actually set -- an engine's
    own hardcoded default (used when `threshold_pct` is None) is left
    alone, since this mode's job is to loosen the user's own configured
    bar, not to silently override every engine's private default.

    Args:
        threshold_pct: The configured threshold (0-100), if any.
        runtime_settings: This cycle's `RuntimeSettings` row.

    Returns:
        `threshold_pct` unchanged when the mode is off or unset; otherwise
        discounted by `_DEMO_LEARNING_THRESHOLD_DISCOUNT_PCT`, floored at
        `_DEMO_LEARNING_MIN_THRESHOLD_PCT`.
    """
    if not runtime_settings.demo_learning_mode_enabled or threshold_pct is None:
        return threshold_pct
    return max(
        _DEMO_LEARNING_MIN_THRESHOLD_PCT, threshold_pct - _DEMO_LEARNING_THRESHOLD_DISCOUNT_PCT
    )


# `SystemLog.source` for the web UI dashboard's "latest scan" snapshot.
_SCAN_SNAPSHOT_SOURCE = "market_scan_snapshot"
# Per the "Why No Trade" production requirement: Scalping and Swing each
# get their own independent snapshot, separate from the primary engine's
# `_SCAN_SNAPSHOT_SOURCE` -- never merged into one row, so each
# strategy's own status/reasons are always distinguishable.
_SCALPING_SNAPSHOT_SOURCE = "scalping_scan_snapshot"
_SWING_SNAPSHOT_SOURCE = "swing_scan_snapshot"
_SHAKKY_SNAPSHOT_SOURCE = "shakky_scan_snapshot"
_SHAKKY_HOLD_SNAPSHOT_SOURCE = "shakky_hold_snapshot"


def _shakky_order_comment(strategy_name: str, trade_id: uuid.UUID) -> str:
    """Build an MT5-safe order comment for a Shakky trade.

    Mirrors `src.workflows.trade.pipeline`'s own (private) order-comment
    builder, duplicated rather than imported since Shakky's execution
    path bypasses `SignalWorkflow` entirely (see `_execute_shakky_trade`).
    """
    short_id = str(trade_id)[:8]
    return f"{strategy_name}{_SHAKKY_STRATEGY_SUFFIX}:{short_id}"[:_SHAKKY_MT5_COMMENT_MAX_LENGTH]


def _micro_scalping_order_comment(strategy_name: str, trade_id: uuid.UUID) -> str:
    """Build an MT5-safe order comment for a Micro Scalping trade.

    Mirrors `_shakky_order_comment` -- this engine also bypasses
    `SignalWorkflow` entirely (see `_execute_micro_scalping_trade`).
    """
    short_id = str(trade_id)[:8]
    return f"{strategy_name}{_MICRO_SCALPING_STRATEGY_SUFFIX}:{short_id}"[
        :_MICRO_SCALPING_MT5_COMMENT_MAX_LENGTH
    ]


def _single_department_vote(name: str, is_buy: bool, confidence: float) -> dict[str, CombinedVote]:
    """Wrap one engine's own bullish/bearish call as a one-department vote.

    Used by `_scalping_decision`/`_swing_decision` so the Trade Quality
    Engine (`src.engines.chief_ai.trade_quality`) can score these engines'
    signals with the same formula the primary (Intraday) engine uses,
    instead of a separate, parallel scoring path.
    """
    return {
        name: CombinedVote(
            bullish_probability=confidence if is_buy else 1.0 - confidence,
            bearish_probability=1.0 - confidence if is_buy else confidence,
            neutral_probability=0.0,
            confidence=confidence,
            quality_grade=grade_from_confidence(confidence),
            strongest_supporting_factors=[],
            strongest_opposing_factors=[],
        )
    }


def _scalping_decision(
    signal: ScalpingSignal, department_reliability: dict[str, float]
) -> ChiefAIDecision:
    """Wrap a `ScalpingSignal` as a `ChiefAIDecision` for `SignalWorkflow.run()`.

    The Scalping Engine makes its own independent BUY/SELL call (see its
    own module docstring); this only adapts its shape to the same
    interface `SignalWorkflow` already accepts, without re-running Chief
    AI's full multi-department evaluation for it.

    Args:
        signal: The Scalping Engine's own signal.
        department_reliability: This cycle's measured department
            reliability scores, so the Trade Quality Engine can weigh the
            "scalping_engine" department the same way it weighs every
            other department.
    """
    is_buy = signal.direction == "buy"
    probability = ProbabilityEstimate(
        bullish_probability=signal.confidence if is_buy else 1.0 - signal.confidence,
        bearish_probability=1.0 - signal.confidence if is_buy else signal.confidence,
        neutral_probability=0.0,
    )
    department_votes = _single_department_vote("scalping_engine", is_buy, signal.confidence)
    return ChiefAIDecision(
        state="BUY" if is_buy else "SELL",
        probability=probability,
        confidence_pct=signal.confidence * 100,
        uncertainty_factors=[],
        reasons=list(signal.reasons),
        supporting_evidence=list(signal.reasons),
        trade_quality=compute_trade_quality(
            probability=probability,
            confidence_pct=signal.confidence * 100,
            department_votes=department_votes,
            department_reliability=department_reliability,
        ),
    )


def _swing_decision(
    signal: SwingSignal, department_reliability: dict[str, float]
) -> ChiefAIDecision:
    """Wrap a `SwingSignal` as a `ChiefAIDecision` for `SignalWorkflow.run()`.

    The Swing Engine makes its own independent BUY/SELL call (see its own
    module docstring); this only adapts its shape to the same interface
    `SignalWorkflow` already accepts, without re-running Chief AI's full
    multi-department evaluation for it.

    Args:
        signal: The Swing Engine's own signal.
        department_reliability: This cycle's measured department
            reliability scores, so the Trade Quality Engine can weigh the
            "swing_engine" department the same way it weighs every other
            department.
    """
    is_buy = signal.direction == "buy"
    probability = ProbabilityEstimate(
        bullish_probability=signal.confidence if is_buy else 1.0 - signal.confidence,
        bearish_probability=1.0 - signal.confidence if is_buy else signal.confidence,
        neutral_probability=0.0,
    )
    department_votes = _single_department_vote("swing_engine", is_buy, signal.confidence)
    return ChiefAIDecision(
        state="BUY" if is_buy else "SELL",
        probability=probability,
        confidence_pct=signal.confidence * 100,
        uncertainty_factors=[],
        reasons=list(signal.reasons),
        supporting_evidence=list(signal.reasons),
        trade_quality=compute_trade_quality(
            probability=probability,
            confidence_pct=signal.confidence * 100,
            department_votes=department_votes,
            department_reliability=department_reliability,
        ),
    )


def _no_signal_decision(
    department_name: str,
    *,
    direction: Literal["buy", "sell"] | None,
    confidence_pct: float,
    reasons: list[str],
    department_reliability: dict[str, float],
) -> ChiefAIDecision:
    """Build a WAIT `ChiefAIDecision` for a Scalping/Swing cycle with no signal.

    Per the "Why No Trade" production requirement: every strategy shows
    "Trade Quality Score. Confidence. Missing confirmations" even when
    no trade opens. Reuses the exact same Trade Quality Engine formula
    `_scalping_decision`/`_swing_decision` use for an actionable signal
    (`compute_trade_quality`), so "why no trade" is scored consistently
    rather than by a separate, ad hoc formula.

    Args:
        department_name: "scalping_engine" or "swing_engine".
        direction: The best directional read this cycle, if any evidence
            was measured at all. None means a fully neutral vote --
            never a fabricated lean when there was nothing to measure.
        confidence_pct: The best measured confidence this cycle, 0-100.
        reasons: Why this cycle did not qualify.
        department_reliability: This cycle's measured department
            reliability scores.
    """
    confidence = confidence_pct / 100.0
    if direction is None:
        probability = ProbabilityEstimate(
            bullish_probability=0.0, bearish_probability=0.0, neutral_probability=1.0
        )
        department_votes: dict[str, CombinedVote] = {
            department_name: CombinedVote(
                bullish_probability=0.0,
                bearish_probability=0.0,
                neutral_probability=1.0,
                confidence=0.0,
                quality_grade="C",
                strongest_supporting_factors=[],
                strongest_opposing_factors=[],
            )
        }
    else:
        is_buy = direction == "buy"
        probability = ProbabilityEstimate(
            bullish_probability=confidence if is_buy else 1.0 - confidence,
            bearish_probability=1.0 - confidence if is_buy else confidence,
            neutral_probability=0.0,
        )
        department_votes = _single_department_vote(department_name, is_buy, confidence)
    return ChiefAIDecision(
        state="WAIT",
        probability=probability,
        confidence_pct=confidence_pct,
        uncertainty_factors=[],
        reasons=list(reasons),
        trade_quality=compute_trade_quality(
            probability=probability,
            confidence_pct=confidence_pct,
            department_votes=department_votes,
            department_reliability=department_reliability,
        ),
    )


def _snapshot_department_votes(
    department_votes: dict[str, CombinedVote],
) -> dict[str, dict[str, float | str]]:
    """Serialize each department's vote into a journal-friendly snapshot.

    Args:
        department_votes: Every department's `CombinedVote` for this cycle.

    Returns:
        `{name: {"bias": "bullish"|"bearish"|"neutral", "confidence": float}}`
        — enough for `src.engines.learning_engine.department_performance`
        to later compare each department's call against the trade's
        realized outcome, without needing to replay the full vote.
    """
    return {
        name: {"bias": vote_bias(vote), "confidence": vote.confidence}
        for name, vote in department_votes.items()
    }


def _extract_trend_bias(technical_vote: CombinedVote | None) -> str | None:
    """Pull the Trend Agent's own bias out of the fused "technical" vote.

    The web UI's "Current Trend" field wants the Trend Agent's own read
    specifically, not the Technical Department's overall fused bias
    (`_snapshot_department_votes`'s "technical" entry already reports
    that separately) -- `CombinedVote.agent_reports` retains every
    individual agent's own `AgentReport`, so this is real data, not a
    fabricated derivation.
    """
    if technical_vote is None:
        return None
    for report in technical_vote.agent_reports:
        if report.agent_name == "trend":
            return report.bias
    return None


def _technical_sub_signals(technical_vote: CombinedVote | None) -> dict[str, list[str]]:
    """Break the fused "technical" vote back down into each agent's own evidence.

    Per the "Complete Strategy Builder" production requirement: "Show all
    internal confirmations inside every module," e.g. Trend -> "✅ EMA20",
    "✅ EMA50", "❌ EMA200" -- `AgentReport.supporting_evidence`/
    `opposing_evidence` already carry this detail per-agent
    (AGENT_SYSTEM.md), this only regroups it for display, never
    recomputing or fabricating a reading no agent actually reported.
    """
    if technical_vote is None:
        return {}
    return {
        report.agent_name: [
            *(f"✅ {evidence}" for evidence in report.supporting_evidence),
            *(f"❌ {evidence}" for evidence in report.opposing_evidence),
        ]
        for report in technical_vote.agent_reports
    }


def _build_dynamic_stop_inputs(scan_result: MarketScanResult) -> DynamicStopInputs:
    """Extract this cycle's real signals for `PositionMonitor`'s dynamic stop logic.

    Reuses exactly what `MarketScanner.scan()` already computed this cycle
    (the Technical Department's own `VolatilityAgent`/`TrendAgent`/
    `SupportResistanceAgent` reports, carried on the "technical"
    `CombinedVote.agent_reports`, plus the Order Flow Engine's vote and
    the classified regime) — never a separate, re-fabricated read.

    Args:
        scan_result: This (or the previous) cycle's `MarketScanner.scan()` result.

    Returns:
        The `DynamicStopInputs` to pass to `PositionMonitor.run_cycle()`.
    """
    technical_vote = scan_result.department_votes.get("technical")
    agent_reports = technical_vote.agent_reports if technical_vote is not None else []
    volatility_report = next((r for r in agent_reports if r.agent_name == "volatility"), None)
    trend_report = next((r for r in agent_reports if r.agent_name == "trend"), None)
    support_resistance_report = next(
        (r for r in agent_reports if r.agent_name == "support_resistance"), None
    )

    order_flow_vote = scan_result.department_votes.get("order_flow")
    order_flow_bias: str | None = None
    order_flow_confidence = 0.0
    if order_flow_vote is not None:
        order_flow_snapshot = _snapshot_department_votes({"order_flow": order_flow_vote})
        order_flow_bias = str(order_flow_snapshot["order_flow"]["bias"])
        order_flow_confidence = float(order_flow_snapshot["order_flow"]["confidence"])

    return DynamicStopInputs(
        atr_ratio=volatility_report.metrics.get("atr_ratio") if volatility_report else None,
        order_flow_bias=order_flow_bias,
        order_flow_confidence=order_flow_confidence,
        htf_trend_bias=trend_report.bias if trend_report is not None else None,
        market_regime=scan_result.market_regime,
        nearest_support=(
            support_resistance_report.metrics.get("nearest_support")
            if support_resistance_report
            else None
        ),
        nearest_resistance=(
            support_resistance_report.metrics.get("nearest_resistance")
            if support_resistance_report
            else None
        ),
        # The News department is unconfigured in this platform's current
        # reduced mode (no NewsAPI key) -- an honest "no elevated signal
        # available" default, not a guess.
        news_risk_imminent=False,
    )


def _apply_runtime_settings(
    config: MarketScanConfig, runtime_settings: RuntimeSettings
) -> MarketScanConfig:
    """Build this cycle's effective scan config from the user's live overrides.

    Per the "User Interface" production requirement: "Settings: Lot Size,
    Auto Trading, Confidence Threshold, Risk Mode" take effect on the very
    next cycle, without a restart.

    Args:
        config: The script's own configured baseline.
        runtime_settings: This cycle's `RuntimeSettings` row.

    Returns:
        `config` with any set overrides applied.
    """
    risk_multiplier = _RISK_MODE_MULTIPLIERS.get(runtime_settings.risk_mode, 1.0)
    confidence_threshold = (
        _demo_learning_discount(runtime_settings.confidence_threshold, runtime_settings)
        if runtime_settings.confidence_threshold is not None
        else config.confidence_threshold
    )
    min_trade_quality_score = (
        _demo_learning_discount(runtime_settings.min_trade_quality_score, runtime_settings)
        if runtime_settings.min_trade_quality_score is not None
        else config.min_trade_quality_score
    )
    return dataclasses.replace(
        config,
        risk_per_trade_pct=config.risk_per_trade_pct * risk_multiplier,
        fixed_lot_size=(
            runtime_settings.fixed_lot_size
            if runtime_settings.fixed_lot_size is not None
            else config.fixed_lot_size
        ),
        confidence_threshold=confidence_threshold,
        min_trade_quality_score=min_trade_quality_score,
        demo_learning_mode=bool(runtime_settings.demo_learning_mode_enabled),
    )


class LiveTradingLoop:
    """Runs the Market Update / Signal / Trade Monitoring workflows on an interval."""

    def __init__(
        self,
        *,
        scan_config: MarketScanConfig,
        mt5_client: MT5Client,
        telegram_notifier: TelegramNotifier,
        technical_agents: list[TechnicalAgent],
        classification_model: ClassificationModel,
        regression_model: RegressionModel,
        session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]],
        interval_seconds: int,
        breakeven_trigger_r_multiple: float = _DEFAULT_BREAKEVEN_TRIGGER_R_MULTIPLE,
        scalping_service: ScalpingAnalysisService | None = None,
        swing_service: SwingAnalysisService | None = None,
        shakky_service: ShakkyAnalysisService | None = None,
        micro_scalping_service: MicroScalpingAnalysisService | None = None,
        session_schedule: SessionSchedule | None = None,
    ) -> None:
        """Initialize the loop (constructor injection).

        Args:
            scan_config: Every tunable input `MarketScanner` needs.
            mt5_client: Shared execution/market-data gateway for the
                loop's lifetime.
            telegram_notifier: Shared notification gateway.
            technical_agents: Every independent Technical Department agent.
            classification_model: Trained direction classifier, held in
                memory for the loop's lifetime
                (`src.engines.ml_engine.training.TrainingService`).
            regression_model: Trained forward-return regressor, held in
                memory for the loop's lifetime.
            session_factory: Callable returning a fresh `AsyncSession`
                context manager per cycle (e.g.
                `src.database.postgres.session.get_session`).
            interval_seconds: Delay between the end of one cycle and the
                start of the next.
            breakeven_trigger_r_multiple: Passed through to `PositionMonitor`.
            scalping_service: The independent Scalping Engine (Phase 22),
                if enabled this cycle. None (the default) disables it
                entirely — no M1/H1 candles are fetched and every cycle
                behaves exactly as before Phase 22, matching the same
                opt-in pattern as `correlation_service`/`order_flow_service`
                on `MarketScanner`.
            swing_service: The independent Swing Engine (Phase 26), if
                enabled this cycle. None (the default) disables it
                entirely — no D1/W1 candles are fetched for it, matching
                `scalping_service`'s own opt-in pattern.
            shakky_service: The independent Classic M5 Strategy Engine
                ("Shakky"), if enabled this cycle. None (the default)
                disables it entirely, matching `scalping_service`'s own
                opt-in pattern. Unlike Scalping/Swing, Shakky never goes
                through `SignalWorkflow`/the Trade Quality Engine (its
                own spec forbids both) — see `_execute_shakky_trade`.
            micro_scalping_service: The independent Micro Scalping Engine,
                if enabled this cycle. None (the default) disables it
                entirely, matching `scalping_service`'s own opt-in
                pattern. Reuses Shakky's own entry-confirmation logic
                internally (`src.engines.micro_scalping_engine.service`)
                with its own additional gates and its own dynamic
                profit-target/trailing exit management -- also bypasses
                `SignalWorkflow`/the Trade Quality Engine, same as Shakky.
            session_schedule: The "Before Market Close" report's schedule
                (`src.engines.risk_engine.session_schedule`). None (the
                default) disables the report entirely.
        """
        self._scan_config = scan_config
        self._mt5 = mt5_client
        self._telegram = telegram_notifier
        self._technical_agents = technical_agents
        self._classification_model = classification_model
        self._regression_model = regression_model
        self._session_factory = session_factory
        self._interval_seconds = interval_seconds
        self._breakeven_trigger_r_multiple = breakeven_trigger_r_multiple
        self._magic_number = compute_magic_number(
            scan_config.strategy_name, scan_config.strategy_version
        )
        self._scalping_magic_number = compute_magic_number(
            f"{scan_config.strategy_name}{_SCALPING_STRATEGY_SUFFIX}", scan_config.strategy_version
        )
        self._swing_magic_number = compute_magic_number(
            f"{scan_config.strategy_name}{_SWING_STRATEGY_SUFFIX}", scan_config.strategy_version
        )
        self._shakky_magic_number = compute_magic_number(
            f"{scan_config.strategy_name}{_SHAKKY_STRATEGY_SUFFIX}", scan_config.strategy_version
        )
        self._micro_scalping_magic_number = compute_magic_number(
            f"{scan_config.strategy_name}{_MICRO_SCALPING_STRATEGY_SUFFIX}",
            scan_config.strategy_version,
        )
        # Order Flow must persist across cycles (it remembers the last DOM
        # snapshot to detect swept liquidity walls); Correlation has no
        # cross-cycle state and is rebuilt each cycle from that cycle's own
        # session-scoped repositories, like every other engine here.
        self._order_flow_service = OrderFlowAnalysisService(mt5_client=mt5_client)
        self._scalping_service = scalping_service
        self._swing_service = swing_service
        self._shakky_service = shakky_service
        self._micro_scalping_service = micro_scalping_service
        self._session_schedule = session_schedule
        # In-memory, per-process state: which calendar date the "Before
        # Market Close" report last ran for, so the 30-minute window
        # doesn't re-send the same report every cycle within it.
        self._last_pre_close_report_date: date | None = None
        self._last_scan_result: MarketScanResult | None = None
        # In-memory, per-process throttle: a WAIT decision recurs almost
        # every cycle, so the "No Trade" Telegram explanation is sent at
        # most once per `_NO_TRADE_TELEGRAM_MIN_INTERVAL` -- a periodic
        # digest, not a message every single cycle.
        self._last_no_trade_telegram_at: datetime | None = None

    async def run_forever(self) -> None:
        """Run cycles back to back, forever, sleeping `interval_seconds` between them."""
        await self._check_startup_reconciliation()
        while True:
            await self.run_once()
            await asyncio.sleep(self._interval_seconds)

    async def _check_startup_reconciliation(self) -> None:
        """Log any mismatch between MT5's real open positions and the trade journal.

        Per an institutional audit finding: nothing previously checked
        whether the two had silently diverged (e.g. after a process crash
        between order placement and journal commit — the same failure
        class already found and fixed once this session for a Telegram
        notification error). Read-only: only logs, per this platform's own
        governance principle of never auto-correcting financial state
        without human review.
        """
        try:
            async with self._session_factory() as session:
                report = await reconcile_positions(
                    mt5_client=self._mt5,
                    trade_repository=TradeRepository(session),
                    mt5_symbol=self._scan_config.mt5_symbol,
                )
        except Exception:
            logger.exception("startup_reconciliation_check_failed")
            return

        if report.is_clean:
            logger.info("startup_reconciliation_clean", matched_count=report.matched_count)
        else:
            logger.warning(
                "startup_reconciliation_mismatch_detected",
                broker_tickets_missing_from_journal=report.broker_tickets_missing_from_journal,
                journal_trades_missing_from_broker=report.journal_trades_missing_from_broker,
            )

    async def run_once(self) -> None:
        """Run exactly one Trade Monitoring + Market Update + Signal cycle.

        Never raises: any failure is logged and the loop continues on its
        next scheduled tick rather than crashing the process, since a
        single bad cycle must not stop ongoing position monitoring.

        Position monitoring and the market scan each run in their own
        `session_factory()` block, committing independently — an
        institutional audit finding: running both in one shared session
        meant a failure in the market scan (e.g. a downstream, non-critical
        error) would roll back *already-succeeded* breakeven-move writes
        from position monitoring too, the same failure class already found
        and fixed once this session (a Telegram notification error rolling
        back a just-written trade journal entry inside `SignalWorkflow`).
        """
        try:
            async with self._session_factory() as session:
                await self._run_position_monitoring(session)
        except Exception:
            logger.exception("live_loop_position_monitoring_failed")

        try:
            async with self._session_factory() as session:
                await self._manage_shakky_positions(session)
        except Exception:
            logger.exception("live_loop_shakky_position_management_failed")

        try:
            async with self._session_factory() as session:
                await self._manage_micro_scalping_positions(session)
        except Exception:
            logger.exception("live_loop_micro_scalping_position_management_failed")

        try:
            async with self._session_factory() as session:
                await self._run_market_scan(session)
        except Exception:
            logger.exception("live_loop_market_scan_failed")

        try:
            async with self._session_factory() as session:
                await self._run_pre_close_report(session)
        except Exception:
            logger.exception("live_loop_pre_close_report_failed")

    async def _run_position_monitoring(self, session: AsyncSession) -> None:
        trade_repository = TradeRepository(session)
        monitor = PositionMonitor(
            mt5_client=self._mt5,
            trade_repository=trade_repository,
            breakeven_trigger_r_multiple=self._breakeven_trigger_r_multiple,
            telegram_notifier=self._telegram,
            telegram_chat_id=self._scan_config.telegram_chat_id,
            post_mortem_service=PostMortemService(
                trade_repository=trade_repository,
                proposal_repository=ImprovementProposalRepository(session),
            ),
            shakky_magic_number=(
                self._shakky_magic_number if self._shakky_service is not None else None
            ),
            micro_scalping_magic_number=(
                self._micro_scalping_magic_number
                if self._micro_scalping_service is not None
                else None
            ),
        )
        dynamic_stop_inputs = (
            _build_dynamic_stop_inputs(self._last_scan_result)
            if self._last_scan_result is not None
            else None
        )
        magic_numbers = [self._magic_number]
        if self._scalping_service is not None:
            magic_numbers.append(self._scalping_magic_number)
        if self._swing_service is not None:
            magic_numbers.append(self._swing_magic_number)
        if self._shakky_service is not None:
            magic_numbers.append(self._shakky_magic_number)
        if self._micro_scalping_service is not None:
            magic_numbers.append(self._micro_scalping_magic_number)
        for magic_number in magic_numbers:
            # Production incident: a manually-closed position stayed
            # journaled as "open" forever, blocking that engine from ever
            # searching for a new trade again (`_strategy_has_open_position`
            # checks this same journal). Root cause: this loop had no
            # per-engine isolation -- one magic number's `run_cycle()`
            # raising (e.g. a transient MT5 read failure) aborted the
            # whole method, so every magic number ordered after it never
            # got its own broker-vs-journal reconciliation that cycle --
            # and if the same failure recurred, never again. Each
            # engine's own reconciliation must never depend on every
            # earlier engine's reconciliation having succeeded first.
            try:
                result = await monitor.run_cycle(
                    mt5_symbol=self._scan_config.mt5_symbol,
                    magic_number=magic_number,
                    dynamic_stop_inputs=dynamic_stop_inputs,
                )
            except Exception:
                logger.exception("position_monitoring_cycle_failed", magic_number=magic_number)
                continue
            if result.moved_to_breakeven:
                logger.info("breakeven_moved", tickets=result.moved_to_breakeven)
            if result.trailed:
                logger.info("stop_trailed", tickets=result.trailed)
            if result.errors:
                logger.warning("breakeven_errors", errors=result.errors)

    async def _manage_shakky_positions(self, session: AsyncSession) -> None:
        """Trend Confidence / Hold Manager / Dynamic TP / Position Scaling for open Shakky trades.

        Per the user's own analysis of a successful trading system
        ("its edge is correctly recognizing large market moves and
        managing them well"): every cycle, each open Shakky position is
        re-assessed with a fresh `assess_trend_confidence`/`assess_hold`
        read, which then feeds `evaluate_exit` (extend the target, take
        partial profit, or close on confirmed exhaustion) and
        `evaluate_scaling` (add to an already-profitable position on
        genuine strength). Runs independently of `_run_position_monitoring`
        (which already applies break-even/trailing-stop uniformly to
        every strategy, Shakky included, via `PositionMonitor`) -- this
        step never touches the stop loss itself, only the target and volume.

        A trade with `entry_trend_confidence_score is None` (entered
        before this feature existed, or Trend Confidence could not be
        computed at entry) is skipped for Dynamic TP/Scaling -- it keeps
        today's fixed-TP behavior untouched, the same "improve it, don't
        replace" guarantee `exit_management.evaluate_exit` itself enforces
        for `minor`/`normal`-confidence entries.
        """
        if self._shakky_service is None:
            return
        runtime_settings = await RuntimeSettingsRepository(session).get_or_create_default()
        if not runtime_settings.shakky_enabled:
            return

        positions = await self._mt5.get_open_positions(
            symbol=self._scan_config.mt5_symbol, magic_number=self._shakky_magic_number
        )
        if not positions:
            return

        (
            m5_candles,
            m15_candles,
            h1_candles,
            h4_candles,
            d1_candles,
            dxy_candles,
        ) = await self._fetch_shakky_candles(session)
        trade_repository = TradeRepository(session)

        for position in positions:
            trade = await trade_repository.get_by_broker_ticket(position.ticket)
            if trade is None or trade.entry_price is None or trade.initial_stop_loss is None:
                continue

            trend_confidence = assess_trend_confidence(
                direction=position.direction,
                entry_price=position.current_price,
                d1_candles=d1_candles,
                h4_candles=h4_candles,
                h1_candles=h1_candles,
                m15_candles=m15_candles,
                m5_candles=m5_candles,
                dxy_candles=dxy_candles,
            )
            hold_assessment = assess_hold(
                position_direction=position.direction,
                trend_confidence=trend_confidence,
                m5_candles=m5_candles,
            )
            await self._record_shakky_hold_snapshot(
                session, trade, trend_confidence=trend_confidence, hold_assessment=hold_assessment
            )
            self._update_shakky_excursion(trade, position)

            if trade.entry_trend_confidence_score is not None:
                if runtime_settings.shakky_dynamic_tp_enabled:
                    await self._apply_shakky_exit_decision(
                        trade=trade,
                        position=position,
                        trend_confidence=trend_confidence,
                        hold_assessment=hold_assessment,
                    )
                if runtime_settings.shakky_scaling_enabled:
                    await self._apply_shakky_scaling_decision(
                        trade=trade,
                        position=position,
                        trend_confidence=trend_confidence,
                        hold_assessment=hold_assessment,
                    )

            await trade_repository.add(trade)

    def _update_shakky_excursion(self, trade: Trade, position: OpenPosition) -> None:
        """Update `Trade.max_favorable_excursion`/`max_adverse_excursion` in place.

        Per the "Strategy Comparison"/"Learning" phases' own needs: the
        largest favorable/adverse price move observed while a position
        was open, tracked incrementally each cycle since MT5 does not
        retain intra-trade price history for later reconstruction.
        """
        assert trade.entry_price is not None
        favorable = (
            position.current_price - trade.entry_price
            if position.direction == "buy"
            else trade.entry_price - position.current_price
        )
        trade.max_favorable_excursion = max(trade.max_favorable_excursion or 0.0, favorable)
        trade.max_adverse_excursion = max(trade.max_adverse_excursion or 0.0, -favorable)

    async def _record_shakky_hold_snapshot(
        self,
        session: AsyncSession,
        trade: Trade,
        *,
        trend_confidence: TrendConfidenceAssessment,
        hold_assessment: HoldAssessment,
    ) -> None:
        """Persist "why still holding" for one open Shakky position, every cycle.

        Mirrors the "Why No Trade" transparency pattern
        (`_record_shakky_snapshot`) for already-open positions -- the web
        UI's own process never sees this loop's in-memory state directly.
        """
        await SystemLogRepository(session).record(
            level="INFO",
            source=_SHAKKY_HOLD_SNAPSHOT_SOURCE,
            event="hold_assessment",
            context={
                "trade_id": str(trade.id),
                "broker_ticket": trade.broker_ticket,
                "trend_confidence_level": trend_confidence.level,
                "trend_confidence_score": round(trend_confidence.score, 1),
                "should_hold": hold_assessment.should_hold,
                "continuation_expected": hold_assessment.continuation_expected,
                "reversal_expected": hold_assessment.reversal_expected,
                "reasons": hold_assessment.reasons,
            },
        )

    async def _apply_shakky_exit_decision(
        self,
        *,
        trade: Trade,
        position: OpenPosition,
        trend_confidence: TrendConfidenceAssessment,
        hold_assessment: HoldAssessment,
    ) -> None:
        assert trade.entry_price is not None
        assert trade.initial_stop_loss is not None
        assert trade.entry_trend_confidence_score is not None
        decision = evaluate_exit(
            direction=position.direction,
            entry_trend_confidence_level=bucket_trend_confidence_level(
                trade.entry_trend_confidence_score
            ),
            trend_confidence=trend_confidence,
            hold_assessment=hold_assessment,
            current_price=position.current_price,
            current_take_profit=trade.take_profit or position.current_price,
            original_risk_distance=abs(trade.entry_price - trade.initial_stop_loss),
            current_volume=position.volume,
        )
        if decision.action == "hold":
            return

        if decision.action == "extend_tp" and decision.new_take_profit is not None:
            modify_result = await self._mt5.modify_order(
                position.ticket, take_profit=decision.new_take_profit
            )
            if not modify_result.success:
                logger.warning(
                    "shakky_tp_extend_failed",
                    ticket=position.ticket,
                    error=modify_result.error_message,
                )
                return
            trade.take_profit = decision.new_take_profit
            logger.info(
                "shakky_tp_extended",
                ticket=position.ticket,
                new_take_profit=decision.new_take_profit,
                reasons=decision.reasons,
            )
            return

        # "close_partial"/"close_full" -- the full-close case reuses
        # `PositionMonitor._reconcile_closed_positions`'s existing
        # broker-vs-journal reconciliation (including its automatic
        # post-mortem) on the next `_run_position_monitoring` cycle
        # rather than duplicating that logic here; this only issues the
        # close order and lets that generic mechanism catch it.
        close_volume = None if decision.action == "close_full" else decision.close_volume
        close_result = await self._mt5.close_position(position.ticket, volume=close_volume)
        if not close_result.success:
            logger.warning(
                "shakky_exit_close_failed", ticket=position.ticket, error=close_result.error_message
            )
            return
        if decision.action == "close_partial" and decision.close_volume is not None:
            trade.volume = max(trade.volume - decision.close_volume, 0.0)
            await self._notify_shakky_position_event(
                trade,
                position,
                event="partial_close",
                reason="Ранний сигнал разворота при сильном тренде — фиксируем часть прибыли",
                volume_change=-decision.close_volume,
            )
        logger.info(
            "shakky_position_closed",
            ticket=position.ticket,
            action=decision.action,
            reasons=decision.reasons,
        )

    async def _apply_shakky_scaling_decision(
        self,
        *,
        trade: Trade,
        position: OpenPosition,
        trend_confidence: TrendConfidenceAssessment,
        hold_assessment: HoldAssessment,
    ) -> None:
        assert trade.entry_price is not None
        assert trade.entry_trend_confidence_score is not None
        account = await self._mt5.get_account_info()
        open_positions = await self._mt5.get_open_positions(symbol=self._scan_config.mt5_symbol)
        exposure_state = exposure_state_from_positions(open_positions, account.equity)

        candidate_size = compute_fixed_lot_position_size(
            fixed_lot_size=position.volume * DEFAULT_SCALE_FRACTION,
            account_equity=account.equity,
            entry_price=position.current_price,
            stop_loss_price=trade.stop_loss,
        )
        exposure_breaches = check_exposure_limits(
            exposure_state, candidate_size.effective_risk_pct, self._scan_config.exposure_limits
        )

        decision = evaluate_scaling(
            direction=position.direction,
            entry_price=trade.entry_price,
            current_price=position.current_price,
            entry_trend_confidence_score=trade.entry_trend_confidence_score,
            current_trend_confidence_score=trend_confidence.score,
            market_structure_valid=not hold_assessment.reversal_expected,
            exposure_breach_reasons=exposure_breaches,
            base_volume=position.volume,
        )
        if not decision.should_scale or decision.additional_volume is None:
            return

        order_result = await self._mt5.place_order(
            OrderRequest(
                symbol=self._scan_config.mt5_symbol,
                order_type=position.direction,
                volume=decision.additional_volume,
                stop_loss=trade.stop_loss,
                take_profit=trade.take_profit,
                magic_number=self._shakky_magic_number,
                comment=_shakky_order_comment(self._scan_config.strategy_name, trade.id),
            )
        )
        if not order_result.success:
            logger.info(
                "shakky_scale_in_rejected", ticket=position.ticket, error=order_result.error_message
            )
            return

        scale_events = list(trade.scale_events or [])
        scale_events.append(
            {
                "price": position.current_price,
                "volume": decision.additional_volume,
                "at": datetime.now(UTC).isoformat(),
            }
        )
        trade.scale_events = scale_events
        trade.volume += decision.additional_volume
        logger.info(
            "shakky_scaled_in",
            ticket=position.ticket,
            additional_volume=decision.additional_volume,
            reasons=decision.reasons,
        )
        await self._notify_shakky_position_event(
            trade,
            position,
            event="scale_in",
            reason="Тренд усилился на уже прибыльной позиции — добавили объём",
            volume_change=decision.additional_volume,
        )

    async def _notify_shakky_position_event(
        self,
        trade: Trade,
        position: OpenPosition,
        *,
        event: str,
        reason: str,
        volume_change: float,
    ) -> None:
        """Send a position-event Telegram notification, if configured.

        Never raises: a notification failure must not undo an already-
        succeeded broker action (same guard as
        `PositionMonitor._notify_breakeven`).
        """
        message = format_position_event_message(
            PositionEventData(
                event=event,
                trade_id=str(trade.id),
                market=position.symbol,
                reason=reason,
                volume_change=volume_change,
                current_price=position.current_price,
            )
        )
        await self._telegram.send_message(self._scan_config.telegram_chat_id, message)

    async def _run_pre_close_report(self, session: AsyncSession) -> None:
        """Send the "Before Market Close" report once per configured window.

        Per the production requirement: 30 minutes before the session
        close, every open position gets a Telegram report. Reuses this
        cycle's already-computed market scan as the "current market
        view" -- never re-fabricates a separate opinion, and never runs
        before at least one market scan has completed this process.
        """
        if self._session_schedule is None or self._last_scan_result is None:
            return

        now = datetime.now(UTC)
        if not is_within_pre_close_window(now, self._session_schedule):
            return
        if has_pre_close_report_already_run_today(self._last_pre_close_report_date, now):
            return

        weekend_approaching = is_weekend_approaching(now, self._session_schedule)
        trade_repository = TradeRepository(session)
        magic_numbers = [self._magic_number]
        if self._scalping_service is not None:
            magic_numbers.append(self._scalping_magic_number)
        if self._swing_service is not None:
            magic_numbers.append(self._swing_magic_number)
        if self._shakky_service is not None:
            magic_numbers.append(self._shakky_magic_number)
        if self._micro_scalping_service is not None:
            magic_numbers.append(self._micro_scalping_magic_number)

        for magic_number in magic_numbers:
            positions = await self._mt5.get_open_positions(
                symbol=self._scan_config.mt5_symbol, magic_number=magic_number
            )
            for position in positions:
                trade = await trade_repository.get_by_broker_ticket(position.ticket)
                if trade is None:
                    continue
                assessment = assess_position_before_close(
                    trade=trade,
                    position=position,
                    current_decision=self._last_scan_result.decision,
                    market_regime=self._last_scan_result.market_regime,
                    weekend_approaching=weekend_approaching,
                )
                await self._telegram.send_message(
                    self._scan_config.telegram_chat_id,
                    format_pre_close_report_message(assessment),
                )

        self._last_pre_close_report_date = now.date()
        logger.info("pre_close_report_sent", weekend_approaching=weekend_approaching)

    async def _run_market_scan(self, session: AsyncSession) -> None:
        runtime_settings = await RuntimeSettingsRepository(session).get_or_create_default()
        if runtime_settings.paused:
            logger.info("market_scan_skipped_paused")
            return
        effective_config = _apply_runtime_settings(self._scan_config, runtime_settings)

        candle_repository = CandleRepository(session)
        await self._refresh_correlated_instruments(session, timeframe=effective_config.timeframe)
        # Per the "Trade Quality Engine" production requirement: "Chief AI
        # must combine these using calibrated weights instead of simple
        # averaging." Recomputed fresh each cycle from recent closed
        # trades, mirroring how `RuntimeSettings` is itself re-read every
        # cycle so learning takes effect without a restart.
        department_reliability = await self._compute_department_reliability(session)
        books_confluence = await self._compute_books_confluence(session)
        try:
            await maybe_generate_recommendations(session)
        except Exception:
            # Per "No production strategy may change automatically": the
            # optimizer only ever proposes, never applies -- a failure
            # here must never block the scan/trading cycle it's riding
            # alongside.
            logger.exception("weight_optimizer_failed")
        # Per the "Complete Strategy Builder" production requirement: the
        # Intraday engine's own assigned profile (if any) filters/weights
        # its technical agents and department-level reliability -- a
        # disabled module really does not vote this cycle, not merely
        # display as disabled.
        intraday_modules = await self._resolve_profile_modules(
            session, runtime_settings.intraday_profile_name
        )
        scanner = MarketScanner(
            config=effective_config,
            mt5_client=self._mt5,
            candle_repository=candle_repository,
            historical_ingestion=MT5HistoricalIngestionService(
                candle_repository=candle_repository, mt5_client=self._mt5
            ),
            similarity_service=HistoricalSimilarityService(
                candle_repository=candle_repository,
                similarity_repository=HistoricalSimilarityRepository(session),
            ),
            technical_agents=apply_profile_to_agents(self._technical_agents, intraday_modules),
            classification_model=self._classification_model,
            regression_model=self._regression_model,
            correlation_service=CorrelationAnalysisService(
                candle_repository=candle_repository,
                correlated_price_repository=CorrelatedPriceRepository(session),
                instrument_repository=CorrelatedInstrumentRepository(session),
            ),
            order_flow_service=self._order_flow_service,
            department_reliability=apply_profile_to_department_reliability(
                department_reliability, intraday_modules
            ),
            books_confluence=books_confluence,
            technical_agent_weights=profile_agent_weights(intraday_modules),
        )
        scan_result = await scanner.scan()
        self._last_scan_result = scan_result
        logger.info(
            "market_scan_completed",
            state=scan_result.decision.state,
            confidence_pct=round(scan_result.decision.confidence_pct, 1),
            regime=scan_result.market_regime,
            blocked_reasons=scan_result.blocked_reasons,
            auto_trading_enabled=runtime_settings.auto_trading_enabled,
        )
        await self._record_scan_snapshot(session, scan_result)
        await self._maybe_send_no_trade_telegram(scan_result)

        # Production incident: `auto_trading_enabled` used to gate this
        # entire block, which meant every independent engine's own
        # analysis and "why no trade" snapshot (not just its execution)
        # silently stopped recording the moment the toggle was turned
        # off -- the dashboard then froze on whatever state each engine
        # last reported (in one real case, Shakky's own last snapshot
        # stayed stuck on "trade_found" for two months while nothing
        # else ever ran). `auto_trading_enabled` must only ever gate
        # placing an order -- analysis and snapshot recording always run
        # so "why no trade" stays honest and current regardless of this
        # toggle. Each engine below checks it itself, right before its
        # own execution call, never before its own analysis.
        #
        # Per the "Multi Strategy" production requirement: "Run all
        # strategies simultaneously... Chief AI must decide independently
        # for every opportunity." Each engine below is evaluated and, if
        # it independently qualifies, executed in this same cycle --
        # never picking only one. `_strategy_has_open_position`/
        # `_portfolio_position_cap_reached` re-query currently-open
        # positions fresh on every call, so an earlier engine's execution
        # this cycle is already reflected in a later engine's own check.
        # Per the "User Configuration" production requirement: any
        # combination of engines is selectable, including excluding
        # Intraday itself (e.g. "Scalping only").
        if runtime_settings.intraday_enabled:
            await self._run_intraday_engine(
                session, scan_result, effective_config, runtime_settings
            )

        if self._scalping_service is not None and runtime_settings.scalping_enabled:
            await self._run_scalping_engine(
                session, scan_result, effective_config, runtime_settings, department_reliability
            )

        if self._swing_service is not None and runtime_settings.swing_enabled:
            await self._run_swing_engine(
                session, effective_config, runtime_settings, department_reliability
            )

        if self._shakky_service is not None and runtime_settings.shakky_enabled:
            await self._run_shakky_engine(session, effective_config, runtime_settings)

        if self._micro_scalping_service is not None and runtime_settings.micro_scalping_enabled:
            await self._run_micro_scalping_engine(session, effective_config, runtime_settings)

    async def _run_intraday_engine(
        self,
        session: AsyncSession,
        scan_result: MarketScanResult,
        effective_config: MarketScanConfig,
        runtime_settings: RuntimeSettings,
    ) -> None:
        """Execute the primary (Intraday) engine's own decision this cycle, if actionable."""
        actionable = (
            scan_result.decision.state
            in (
                "BUY",
                "SELL",
            )
            and not scan_result.blocked_reasons
        )
        if not actionable:
            return
        # Defensive: MarketScanner always sets all four together for an
        # unblocked BUY/SELL result; guards a future contract violation
        # rather than a path this test suite can reach today.
        if (
            scan_result.entry_price is None
            or scan_result.stop_loss is None
            or scan_result.position_size is None
            or scan_result.execution_request is None
        ):  # pragma: no cover
            logger.warning("actionable_decision_missing_trade_parameters")
            return

        if await self._strategy_has_open_position(session, self._magic_number):
            logger.info("signal_suppressed_intraday_already_has_open_position")
            return
        if await self._portfolio_position_cap_reached(session, runtime_settings):
            logger.info("signal_suppressed_portfolio_position_cap_reached")
            return
        if not runtime_settings.auto_trading_enabled:
            logger.info("signal_suppressed_auto_trading_disabled")
            return

        signal_workflow = SignalWorkflow(
            trade_repository=TradeRepository(session),
            mt5_client=self._mt5,
            telegram_notifier=self._telegram,
        )
        workflow_input = SignalWorkflowInput(
            symbol_id=effective_config.symbol_id,
            market_symbol_name=effective_config.mt5_symbol,
            entry_price=scan_result.entry_price,
            stop_loss=scan_result.stop_loss,
            take_profit=scan_result.take_profit,
            position_size=scan_result.position_size,
            execution_request=scan_result.execution_request,
            strategy_name=effective_config.strategy_name,
            strategy_version=effective_config.strategy_version,
            telegram_chat_id=effective_config.telegram_chat_id,
            department_votes=_snapshot_department_votes(scan_result.department_votes),
            market_regime=scan_result.market_regime,
            similarity_summary=scan_result.similarity_summary,
        )
        result = await signal_workflow.run(scan_result.decision, workflow_input)
        logger.info(
            "signal_workflow_completed",
            executed=result.executed,
            rejection_reasons=result.rejection_reasons,
            telegram_sent=result.telegram_sent,
        )

    async def _run_scalping_engine(
        self,
        session: AsyncSession,
        scan_result: MarketScanResult,
        effective_config: MarketScanConfig,
        runtime_settings: RuntimeSettings,
        department_reliability: dict[str, float],
    ) -> None:
        """Run the Scalping Engine's own independent analysis and execute if it qualifies."""
        outcome = await self._run_scalping_analysis(
            session,
            correlation_vote=scan_result.department_votes.get("correlation"),
            confidence_threshold_pct=_demo_learning_discount(
                runtime_settings.scalping_confidence_threshold, runtime_settings
            ),
        )
        # Per the "Why No Trade" production requirement: every strategy's
        # own cycle outcome is recorded, whether or not it goes on to
        # execute -- never silently discarded.
        quality_score = await self._record_strategy_snapshot(
            session,
            source=_SCALPING_SNAPSHOT_SOURCE,
            department_name="scalping_engine",
            outcome_reasons=outcome.reasons,
            outcome_direction=outcome.direction,
            outcome_confidence_pct=outcome.confidence_pct,
            has_signal=outcome.signal is not None,
            department_reliability=department_reliability,
            min_trade_quality_score=effective_config.min_trade_quality_score,
        )
        if outcome.signal is None:
            return
        # Per the "Trade Quality Engine" production requirement: the
        # score is the primary decision metric for every strategy, not
        # just Intraday -- a signal that cleared its own confidence
        # threshold can still be rejected on quality.
        if quality_score < effective_config.min_trade_quality_score:
            logger.info(
                "scalp_signal_suppressed_trade_quality_below_threshold",
                quality_score=quality_score,
                threshold=effective_config.min_trade_quality_score,
            )
            return
        if await self._strategy_has_open_position(session, self._scalping_magic_number):
            logger.info("scalp_signal_suppressed_scalping_already_has_open_position")
            return
        if await self._portfolio_position_cap_reached(session, runtime_settings):
            logger.info("scalp_signal_suppressed_portfolio_position_cap_reached")
            return
        if not runtime_settings.auto_trading_enabled:
            logger.info("scalp_signal_suppressed_auto_trading_disabled")
            return
        await self._execute_scalping_trade(
            session, outcome.signal, effective_config, department_reliability
        )

    async def _run_swing_engine(
        self,
        session: AsyncSession,
        effective_config: MarketScanConfig,
        runtime_settings: RuntimeSettings,
        department_reliability: dict[str, float],
    ) -> None:
        """Run the Swing Engine's own independent analysis and execute if it qualifies."""
        swing_modules = await self._resolve_profile_modules(
            session, runtime_settings.swing_profile_name
        )
        outcome = await self._run_swing_analysis(
            session,
            confidence_threshold_pct=_demo_learning_discount(
                runtime_settings.swing_confidence_threshold, runtime_settings
            ),
            modules=swing_modules,
        )
        quality_score = await self._record_strategy_snapshot(
            session,
            source=_SWING_SNAPSHOT_SOURCE,
            department_name="swing_engine",
            outcome_reasons=outcome.reasons,
            outcome_direction=outcome.direction,
            outcome_confidence_pct=outcome.confidence_pct,
            has_signal=outcome.signal is not None,
            department_reliability=department_reliability,
            min_trade_quality_score=effective_config.min_trade_quality_score,
        )
        if outcome.signal is None:
            return
        # Per the "Trade Quality Engine" production requirement: the
        # score is the primary decision metric for every strategy, not
        # just Intraday -- a signal that cleared its own confidence
        # threshold can still be rejected on quality.
        if quality_score < effective_config.min_trade_quality_score:
            logger.info(
                "swing_signal_suppressed_trade_quality_below_threshold",
                quality_score=quality_score,
                threshold=effective_config.min_trade_quality_score,
            )
            return
        if await self._strategy_has_open_position(session, self._swing_magic_number):
            logger.info("swing_signal_suppressed_swing_already_has_open_position")
            return
        if await self._portfolio_position_cap_reached(session, runtime_settings):
            logger.info("swing_signal_suppressed_portfolio_position_cap_reached")
            return
        if not runtime_settings.auto_trading_enabled:
            logger.info("swing_signal_suppressed_auto_trading_disabled")
            return
        await self._execute_swing_trade(
            session, outcome.signal, effective_config, department_reliability
        )

    async def _run_shakky_engine(
        self,
        session: AsyncSession,
        effective_config: MarketScanConfig,
        runtime_settings: RuntimeSettings,
    ) -> None:
        """Run the Classic M5 Strategy ("Shakky") Engine and execute if it qualifies.

        Per Shakky's own production requirement ("must NOT use Chief AI
        decision logic, the Trade Quality Engine, Books Intelligence,
        Machine Learning, Historical Pattern Matching, the News Engine,
        the Correlation Engine (except DXY), Smart Money, Order Flow, or
        any existing AI scoring"): unlike Scalping/Swing, there is no
        Trade Quality Score to gate on here -- Shakky's own minimum-3-
        confirmations rule (already enforced inside
        `ShakkyAnalysisService.analyze()`) is its entire quality gate.

        On top of that, execution additionally requires the same
        deterministic Trend Confidence Engine Shakky already computes
        every cycle (for its own post-entry Dynamic TP/Scaling) to read
        "strong" or "exceptional" -- per the explicit "fewer, higher-
        quality trades" direction: real historical performance across
        every engine on this account showed a negative edge at the
        baseline 3-confirmation bar alone (profit factor well under 1.0
        across hundreds of trades), so the bar for Shakky's own
        *execution* is raised without touching its own tested entry
        logic. `trend_confidence` is never fabricated for this -- it is
        None whenever `assess_trend_confidence` could not be computed
        (e.g. no DXY data), and a signal is honestly skipped rather than
        guessed through in that case.
        """
        outcome, trend_confidence = await self._run_shakky_analysis(session)
        await self._record_shakky_snapshot(session, outcome)
        if outcome.signal is None:
            return
        if trend_confidence is None or trend_confidence.level not in ("strong", "exceptional"):
            logger.info(
                "shakky_signal_suppressed_trend_confidence_below_bar",
                level=trend_confidence.level if trend_confidence is not None else None,
            )
            return
        if await self._strategy_has_open_position(session, self._shakky_magic_number):
            logger.info("shakky_signal_suppressed_shakky_already_has_open_position")
            return
        if await self._portfolio_position_cap_reached(session, runtime_settings):
            logger.info("shakky_signal_suppressed_portfolio_position_cap_reached")
            return
        if not runtime_settings.auto_trading_enabled:
            logger.info("shakky_signal_suppressed_auto_trading_disabled")
            return
        await self._execute_shakky_trade(
            session, outcome.signal, effective_config, trend_confidence
        )

    async def _run_micro_scalping_engine(
        self,
        session: AsyncSession,
        effective_config: MarketScanConfig,
        runtime_settings: RuntimeSettings,
    ) -> None:
        """Run the Micro Scalping Engine and execute if it qualifies.

        Per its own spec ("Reuse the existing Shakky confirmation
        logic... Do NOT invent a new strategy"): also bypasses
        `SignalWorkflow`/the Trade Quality Engine entirely, same as
        Shakky -- its own additional gates
        (`src.engines.micro_scalping_engine.entry_filters`) plus its own
        Trend Confidence-based minimum confidence are its entire quality gate.
        """
        outcome = await self._run_micro_scalping_analysis(session, runtime_settings)
        await self._record_micro_scalping_snapshot(session, outcome)
        if outcome.signal is None:
            return
        if await self._strategy_has_open_position(session, self._micro_scalping_magic_number):
            logger.info("micro_scalping_signal_suppressed_already_has_open_position")
            return
        if await self._portfolio_position_cap_reached(session, runtime_settings):
            logger.info("micro_scalping_signal_suppressed_portfolio_position_cap_reached")
            return
        if not runtime_settings.auto_trading_enabled:
            logger.info("micro_scalping_signal_suppressed_auto_trading_disabled")
            return
        await self._execute_micro_scalping_trade(
            session,
            outcome.signal,
            effective_config,
            runtime_settings,
            outcome.trend_confidence_score,
        )

    async def _record_scan_snapshot(
        self, session: AsyncSession, scan_result: MarketScanResult
    ) -> None:
        """Persist this cycle's decision as a durable, queryable snapshot.

        Per the "User Interface" production requirement's main page
        ("Current Market, Confidence, Active Strategy... AI Explanation"):
        the web UI runs in a separate process and has no access to this
        loop's in-memory `self._last_scan_result`, so the latest snapshot
        must be durably persisted -- reuses `SystemLog`
        (DATABASE.md `system_logs`) rather than inventing a new table.
        """
        explanation = explain_decision(scan_result.decision)
        department_votes_snapshot = _snapshot_department_votes(scan_result.department_votes)
        await SystemLogRepository(session).record(
            level="INFO",
            source=_SCAN_SNAPSHOT_SOURCE,
            event="scan_completed",
            context={
                "market": self._scan_config.mt5_symbol,
                "state": scan_result.decision.state,
                "confidence_pct": scan_result.decision.confidence_pct,
                "market_regime": scan_result.market_regime,
                "strategy_name": self._scan_config.strategy_name,
                "explanation": f"{explanation.why_now} {explanation.why_not_opposite}",
                "department_votes": department_votes_snapshot,
                "current_trend": _extract_trend_bias(scan_result.department_votes.get("technical")),
                # Per the "Complete Strategy Builder" production
                # requirement: "Show all internal confirmations inside
                # every module" -- the web UI runs as a separate process
                # and only ever sees this durable snapshot, never the
                # live `CombinedVote.agent_reports` in memory.
                "sub_signals": _technical_sub_signals(
                    scan_result.department_votes.get("technical")
                ),
                "trade_quality_score": scan_result.decision.trade_quality.score,
                "risk_score": scan_result.decision.trade_quality.risk_score,
                # Per the "No Trade Explanation" production requirement:
                # shown in the interface as well as Telegram, from the
                # exact same reasons -- never a second, divergent narrative.
                "no_trade_reasons": (
                    build_no_trade_reasons_ru(scan_result.decision, department_votes_snapshot)
                    if scan_result.decision.state == "WAIT"
                    else []
                ),
                "next_scan_minutes": self._interval_seconds / 60,
                # Per the "Main Dashboard" production requirement's "MT5
                # Status": the web UI's own process never touches MT5
                # directly, so this cycle's own real connectivity check is
                # the only honest source for that field.
                "mt5_connected": await self._mt5.is_connected(),
            },
        )

    async def _record_strategy_snapshot(
        self,
        session: AsyncSession,
        *,
        source: str,
        department_name: str,
        outcome_reasons: list[str],
        outcome_direction: Literal["buy", "sell"] | None,
        outcome_confidence_pct: float,
        has_signal: bool,
        department_reliability: dict[str, float],
        min_trade_quality_score: float,
    ) -> float:
        """Persist one independent strategy's own cycle outcome as a snapshot.

        Per the "Why No Trade" production requirement: "For every
        strategy independently show: Trade not opened. Reasons. Trade
        Quality Score. Confidence. Missing confirmations. This must be
        visible in both the interface and logs." Separate from
        `_record_scan_snapshot` (the primary/Intraday engine's own row)
        -- Scalping and Swing each get their own durable row, using the
        same Trade Quality Engine formula (`_no_signal_decision`) so
        every strategy's score is computed consistently.

        Args:
            session: This cycle's database session.
            source: `_SCALPING_SNAPSHOT_SOURCE` or `_SWING_SNAPSHOT_SOURCE`.
            department_name: "scalping_engine" or "swing_engine".
            outcome_reasons: The cycle's own contributing/blocking factors.
            outcome_direction: The best directional read this cycle, if any.
            outcome_confidence_pct: The best measured confidence this cycle.
            has_signal: Whether this cycle produced an actionable signal
                (regardless of whether it went on to actually execute --
                position/exposure/auto-trading suppression is still only
                logged, not shown as "no trade", since those reflect
                portfolio/operational state rather than this signal's
                own quality).
            department_reliability: This cycle's measured department
                reliability scores.
            min_trade_quality_score: `effective_config.min_trade_quality_score`
                -- a signal below this is shown as "no_trade" with an
                honest reason, exactly the verdict the caller's own
                follow-up check will enforce right after.

        Returns:
            This cycle's own Trade Quality Score (0-100), so the caller
            can also gate execution on it (`min_trade_quality_score`)
            without a second, divergent computation.
        """
        decision = _no_signal_decision(
            department_name,
            direction=outcome_direction,
            confidence_pct=outcome_confidence_pct,
            reasons=outcome_reasons,
            department_reliability=department_reliability,
        )
        quality_score = decision.trade_quality.score
        # Production incident: this used to report "trade_found" purely
        # from `has_signal`, before the caller's own separate
        # `quality_score < min_trade_quality_score` check could veto
        # execution right after -- the dashboard then showed "сделка
        # найдена" for a signal that was never actually going to trade,
        # with the real reason only ever reaching a log line nobody
        # saw. The snapshot must reflect the same verdict the caller
        # will actually act on.
        will_execute = has_signal and quality_score >= min_trade_quality_score
        if has_signal and not will_execute:
            reasons_shown = [
                f"trade_quality_score_below_threshold:{quality_score:.1f}<{min_trade_quality_score:.1f}"
            ]
        elif has_signal:
            reasons_shown = []
        else:
            reasons_shown = build_no_trade_reasons_ru(decision, {})
        await SystemLogRepository(session).record(
            level="INFO",
            source=source,
            event="scan_completed",
            context={
                "market": self._scan_config.mt5_symbol,
                "state": "trade_found" if will_execute else "no_trade",
                "confidence_pct": decision.confidence_pct,
                "trade_quality_score": quality_score,
                "reasons": reasons_shown,
                "next_scan_minutes": self._interval_seconds / 60,
            },
        )
        return quality_score

    async def _record_shakky_snapshot(
        self, session: AsyncSession, outcome: ShakkyAnalysisOutcome
    ) -> None:
        """Persist Shakky's own cycle outcome as a snapshot.

        Per the "Why No Trade" production requirement, mirrors
        `_record_strategy_snapshot`'s role for Scalping/Swing -- except
        Shakky never calls the Trade Quality Engine (`compute_trade_quality`),
        since its own spec explicitly forbids it. `trade_quality_score` and
        `confidence_pct` are honestly omitted rather than fabricated by
        reusing that formula for a signal that was never scored by it.
        """
        await SystemLogRepository(session).record(
            level="INFO",
            source=_SHAKKY_SNAPSHOT_SOURCE,
            event="scan_completed",
            context={
                "market": self._scan_config.mt5_symbol,
                "state": "trade_found" if outcome.signal is not None else "no_trade",
                "direction": outcome.direction,
                "confirmation_count": outcome.confirmation_count,
                "dominant_family": (
                    outcome.signal.dominant_family if outcome.signal is not None else None
                ),
                "reasons": outcome.reasons,
                "next_scan_minutes": self._interval_seconds / 60,
            },
        )

    async def _record_micro_scalping_snapshot(
        self, session: AsyncSession, outcome: MicroScalpingAnalysisOutcome
    ) -> None:
        """Persist Micro Scalping's own cycle outcome as a snapshot.

        Per the "Why No Trade" production requirement, mirrors
        `_record_shakky_snapshot` -- this engine also bypasses the Trade
        Quality Engine entirely, but unlike Shakky it does have its own
        genuine 0-100 confidence read (`trend_confidence_score`), so that
        is honestly surfaced here instead of being omitted.
        """
        await SystemLogRepository(session).record(
            level="INFO",
            source=_MICRO_SCALPING_SNAPSHOT_SOURCE,
            event="scan_completed",
            context={
                "market": self._scan_config.mt5_symbol,
                "state": "trade_found" if outcome.signal is not None else "no_trade",
                "direction": outcome.direction,
                "confirmation_count": outcome.confirmation_count,
                "confidence_pct": outcome.trend_confidence_score,
                "dominant_family": (
                    outcome.signal.dominant_family if outcome.signal is not None else None
                ),
                "reasons": outcome.reasons,
                "next_scan_minutes": self._interval_seconds / 60,
            },
        )

    async def _maybe_send_no_trade_telegram(self, scan_result: MarketScanResult) -> None:
        """Send the "No Trade" Telegram explanation, throttled to a periodic digest.

        Per the "No Trade Explanation" production requirement: whenever
        Chief AI decides not to trade, explain why -- in Telegram as well
        as the interface (the web UI reads the same durable scan
        snapshot `_record_scan_snapshot` already persists). Throttled to
        `_NO_TRADE_TELEGRAM_MIN_INTERVAL` since WAIT recurs almost every
        cycle and a message every cycle would be spam, not a digest.
        """
        if scan_result.decision.state != "WAIT":
            return

        now = datetime.now(UTC)
        if (
            self._last_no_trade_telegram_at is not None
            and now - self._last_no_trade_telegram_at < _NO_TRADE_TELEGRAM_MIN_INTERVAL
        ):
            return

        message = format_no_trade_message(
            NoTradeMessageData(
                market=self._scan_config.mt5_symbol,
                quality_score=scan_result.decision.trade_quality.score,
                confidence_pct=scan_result.decision.confidence_pct,
                reasons=build_no_trade_reasons_ru(
                    scan_result.decision,
                    _snapshot_department_votes(scan_result.department_votes),
                ),
                next_scan_minutes=self._interval_seconds / 60,
            )
        )
        await self._telegram.send_message(self._scan_config.telegram_chat_id, message)
        self._last_no_trade_telegram_at = now

    @staticmethod
    async def _portfolio_position_cap_reached(
        session: AsyncSession, runtime_settings: RuntimeSettings
    ) -> bool:
        """Check the "Max Positions" setting against currently open positions.

        Per the "Settings" production requirement: "Max Positions" is a
        hard count limit, independent of and in addition to the Risk
        Engine's own percentage-based exposure limits
        (`src.engines.risk_engine.exposure`). None means no count limit.

        Per the "Parallel Strategy Execution" production requirement,
        this is a PORTFOLIO-WIDE cap only -- it never singles out one
        strategy. Each engine also checks its own single-position limit
        separately via `_strategy_has_open_position`, so "no other
        strategy blocks this one" and "the user's overall ceiling is
        still respected" are two independent, composable gates.

        Per the "Demo Learning Mode" production requirement's "allow
        parallel trades... maximum statistically useful trading
        experience": while that mode is enabled, this optional ceiling is
        skipped entirely -- each strategy's own single-position limit
        still applies unconditionally, so this never removes ALL position
        limits, only the extra portfolio-wide one.
        """
        if runtime_settings.demo_learning_mode_enabled:
            return False
        if runtime_settings.max_positions is None:
            return False
        open_count = len(await TradeRepository(session).list_open())
        return open_count >= runtime_settings.max_positions

    @staticmethod
    async def _strategy_has_open_position(session: AsyncSession, magic_number: int) -> bool:
        """Check whether this specific strategy already has its own open position.

        Per the "Parallel Strategy Execution" production requirement:
        "Scalping may have only one active Scalping position... Never
        block one strategy because another strategy already has an
        active trade." Each strategy is identified by its own distinct
        magic number (`self._magic_number`/`self._scalping_magic_number`/
        `self._swing_magic_number`), so this only ever counts THAT
        strategy's own trades -- never the portfolio total.
        """
        return await TradeRepository(session).count_open_by_magic_number(magic_number) > 0

    async def _refresh_correlated_instruments(
        self, session: AsyncSession, *, timeframe: str
    ) -> None:
        """Top up every enabled correlated instrument's recent candles this cycle.

        Per the "Correlation Engine" production requirement: "Calculate
        dynamic correlations. Never use fixed assumptions." Without this,
        `CorrelationAnalysisService.analyze()` would only ever see
        whichever snapshot `scripts/correlation_backfill.py` last loaded
        -- a static read, not a dynamically updated one. Mirrors the
        primary symbol's own per-cycle top-up
        (`MT5HistoricalIngestionService`), one instrument at a time so a
        single broker-side failure (e.g. a symbol temporarily unavailable)
        never blocks the others.
        """
        instruments = await CorrelatedInstrumentRepository(session).list_enabled_with_mt5_symbol()
        ingestion = CorrelatedInstrumentIngestionService(
            price_repository=CorrelatedPriceRepository(session), mt5_client=self._mt5
        )
        for instrument in instruments:
            assert instrument.mt5_symbol is not None  # guaranteed by list_enabled_with_mt5_symbol
            try:
                await ingestion.ingest(
                    instrument.id,
                    mt5_symbol=instrument.mt5_symbol,
                    timeframe=timeframe,
                    count=_CORRELATED_INSTRUMENT_TOPUP_COUNT,
                )
            except Exception:
                logger.exception(
                    "correlated_instrument_refresh_failed",
                    instrument=instrument.name,
                    mt5_symbol=instrument.mt5_symbol,
                )

    async def _resolve_profile_modules(
        self, session: AsyncSession, profile_name: str | None
    ) -> dict[str, ModuleSetting]:
        """Load one strategy's assigned Strategy Builder profile as module settings.

        Args:
            session: This cycle's database session.
            profile_name: `RuntimeSettings.intraday_profile_name` /
                `scalping_profile_name` / `swing_profile_name`.

        Returns:
            An empty dict (meaning "every module stays at its default
            behavior") when no profile is assigned, or the assigned
            profile no longer exists (e.g. deleted after being assigned)
            -- an assignment pointing nowhere behaves exactly like no
            assignment, never raises mid-cycle.
        """
        if profile_name is None:
            return {}
        profile = await StrategyProfileRepository(session).get_by_name(profile_name)
        if profile is None:
            return {}
        return {
            module.module_name: ModuleSetting(
                enabled=module.enabled, weight=module.weight, min_confidence=module.min_confidence
            )
            for module in profile.modules
        }

    async def _compute_department_reliability(self, session: AsyncSession) -> dict[str, float]:
        """Measure every department's realized directional accuracy from recent closed trades.

        Per the "Trade Quality Engine" production requirement: "Chief AI
        must combine these using calibrated weights instead of simple
        averaging." Recomputed every cycle (mirroring `RuntimeSettings`'s
        own per-cycle re-read) so a department's weight adapts as more
        outcomes accumulate, without requiring a restart.

        Per the "AI Weight Optimizer" production requirement: a
        department with a user-approved `DepartmentWeightOverride` uses
        that pinned value instead of the freshly computed score --
        everything else still adapts automatically, since only an
        explicit approval (never this per-cycle recompute) can pin a
        weight (`src.engines.learning_engine.weight_optimizer`).
        """
        closed_trades = await TradeRepository(session).list_by_status(
            "closed", limit=_RELIABILITY_LOOKBACK_TRADES
        )
        computed = compute_department_reliability_scores(closed_trades)
        overrides = await DepartmentWeightOverrideRepository(session).get_all()
        return {**computed, **overrides}

    async def _compute_books_confluence(self, session: AsyncSession) -> float:
        """Measure how much validated book knowledge currently supports trading.

        Per the "Trade Quality Engine" production requirement's Books
        Intelligence input. `BookClaim` starts `pending` and is only ever
        moved to `accepted` by the Historical Research Engine's
        statistical validation (a later roadmap phase, per
        `src.models.book_claim`) -- honestly 0.0 (no contribution) until
        that validation has actually accepted claims, never a fabricated
        boost from unvalidated or absent claims.
        """
        accepted_claims = await BookClaimRepository(session).list_by_status(
            "accepted", limit=_BOOKS_CONFLUENCE_SATURATION_COUNT
        )
        return min(1.0, len(accepted_claims) / _BOOKS_CONFLUENCE_SATURATION_COUNT)

    async def _similarity_summary_for_direction(
        self,
        session: AsyncSession,
        *,
        timeframe: str,
        direction: Literal["buy", "sell"],
    ) -> SimilarityDisplayStats:
        """Run the Trade Similarity Engine for one strategy's own chosen direction.

        Per the "Trade Similarity Engine" production requirement: "Before
        opening every trade search the historical database... Display
        this information before every trade." Scalping/Swing each run
        their own independent search against their own entry timeframe
        and already-chosen direction, rather than reusing Intraday's own
        `MarketScanner`-computed summary (searched against a different
        timeframe).
        """
        similarity_service = HistoricalSimilarityService(
            candle_repository=CandleRepository(session),
            similarity_repository=HistoricalSimilarityRepository(session),
        )
        result = await similarity_service.search(
            self._scan_config.symbol_id, timeframe, forward_bars=_SIMILARITY_FORWARD_BARS
        )
        return summarize_matches_for_direction(
            result.matches,
            direction,
            forward_bars=_SIMILARITY_FORWARD_BARS,
            timeframe=timeframe,
        )

    async def _run_scalping_analysis(
        self,
        session: AsyncSession,
        *,
        correlation_vote: CombinedVote | None,
        confidence_threshold_pct: float | None,
    ) -> ScalpingAnalysisOutcome:
        """Fetch fresh M1/H1 data and run the Scalping Engine for this cycle.

        M1/H1 are ingested and read back through the same
        `MT5HistoricalIngestionService` + `CandleRepository` path every
        other timeframe in this platform uses (MULTI TIMEFRAME: "Every
        analysis must include... M1"), rather than bypassing storage.

        Args:
            session: This cycle's database session.
            correlation_vote: The primary engine's own correlation vote,
                if available.
            confidence_threshold_pct: `RuntimeSettings.scalping_confidence_threshold`
                (0-100), if the user has overridden it this cycle. None
                uses the Scalping Engine's own constructed default.
        """
        assert self._scalping_service is not None
        candle_repository = CandleRepository(session)
        ingestion = MT5HistoricalIngestionService(
            candle_repository=candle_repository, mt5_client=self._mt5
        )
        await ingestion.ingest(
            self._scan_config.symbol_id,
            mt5_symbol=self._scan_config.mt5_symbol,
            timeframe="M1",
            count=_SCALPING_M1_CANDLE_COUNT,
        )
        await ingestion.ingest(
            self._scan_config.symbol_id,
            mt5_symbol=self._scan_config.mt5_symbol,
            timeframe=_SCALPING_HTF_TIMEFRAME,
            count=_SCALPING_HTF_CANDLE_COUNT,
        )
        await ingestion.ingest(
            self._scan_config.symbol_id,
            mt5_symbol=self._scan_config.mt5_symbol,
            timeframe="M15",
            count=_SCALPING_M15_CANDLE_COUNT,
        )
        await ingestion.ingest(
            self._scan_config.symbol_id,
            mt5_symbol=self._scan_config.mt5_symbol,
            timeframe="M5",
            count=_SCALPING_M5_CANDLE_COUNT,
        )
        m1_candles = await candle_repository.list_most_recent(
            self._scan_config.symbol_id, "M1", count=_SCALPING_M1_CANDLE_COUNT
        )
        htf_candles = await candle_repository.list_most_recent(
            self._scan_config.symbol_id, _SCALPING_HTF_TIMEFRAME, count=_SCALPING_HTF_CANDLE_COUNT
        )
        m15_candles = await candle_repository.list_most_recent(
            self._scan_config.symbol_id, "M15", count=_SCALPING_M15_CANDLE_COUNT
        )
        m5_candles = await candle_repository.list_most_recent(
            self._scan_config.symbol_id, "M5", count=_SCALPING_M5_CANDLE_COUNT
        )
        tick = await self._mt5.get_symbol_tick(self._scan_config.mt5_symbol)
        return await self._scalping_service.analyze(
            mt5_symbol=self._scan_config.mt5_symbol,
            m1_candles=m1_candles,
            htf_candles=htf_candles,
            tick=tick,
            correlation_vote=correlation_vote,
            confidence_threshold=(
                confidence_threshold_pct / 100.0 if confidence_threshold_pct is not None else None
            ),
            m15_candles=m15_candles,
            m5_candles=m5_candles,
        )

    async def _execute_scalping_trade(
        self,
        session: AsyncSession,
        signal: ScalpingSignal,
        effective_config: MarketScanConfig,
        department_reliability: dict[str, float],
    ) -> None:
        """Size and execute a Scalping Engine signal via the same `SignalWorkflow`.

        Uses a distinct `strategy_name` (and therefore magic number) from
        the primary engine so scalp trades are always separately
        identifiable in MT5 and the journal, and dynamic risk-scaled
        sizing per `src.engines.scalping_engine.position_sizing` — "Lot
        size must NEVER increase simply because the expected movement is
        small."

        Args:
            session: This cycle's database session.
            signal: The Scalping Engine's own signal.
            effective_config: This cycle's config, with the user's live
                Risk Mode override already applied to `risk_per_trade_pct`.
            department_reliability: This cycle's measured department
                reliability scores, for the Trade Quality Engine.
        """
        account = await self._mt5.get_account_info()
        tick = await self._mt5.get_symbol_tick(effective_config.mt5_symbol)
        scaled_risk_pct = compute_scalping_risk_pct(
            effective_config.risk_per_trade_pct,
            ScalpingRiskFactors(
                confidence=signal.confidence,
                spread_points=(tick.ask - tick.bid) / _POINT_SIZE,
                max_acceptable_spread_points=effective_config.max_spread_points,
                # Not yet enough scalping trade history to measure a
                # realized win rate this cycle -- never a fabricated value.
                recent_win_rate=None,
            ),
        )
        position_size = compute_position_size(
            account_equity=account.equity,
            risk_per_trade_pct=scaled_risk_pct,
            entry_price=signal.entry_price,
            stop_loss_price=signal.stop_loss,
        )
        if position_size.position_size_units <= 0:
            logger.info("scalping_trade_skipped", reason="zero_position_size")
            return

        # Per the "Parallel Strategy Execution" production requirement:
        # "Chief AI must evaluate total portfolio exposure before
        # approving additional positions" -- previously only the primary
        # (Intraday) engine ran this check (inside `MarketScanner.scan()`);
        # Scalping hardcoded `risk_approved=True` and never looked at the
        # portfolio's combined exposure across all three engines' trades.
        open_positions = await self._mt5.get_open_positions(symbol=effective_config.mt5_symbol)
        exposure_state = exposure_state_from_positions(open_positions, account.equity)
        exposure_breaches = check_exposure_limits(
            exposure_state, position_size.effective_risk_pct, effective_config.exposure_limits
        )
        if exposure_breaches:
            logger.info(
                "scalping_trade_skipped", reason="exposure_limit", breaches=exposure_breaches
            )
            return

        execution_request = ExecutionValidationRequest(
            expected_symbol=effective_config.mt5_symbol,
            order_symbol=effective_config.mt5_symbol,
            expected_account=effective_config.expected_account,
            actual_account=str(account.login),
            account_type=effective_config.account_type,
            live_trading_approved=effective_config.live_trading_approved,
            is_terminal_connected=await self._mt5.is_connected(),
            is_market_open=True,
            risk_approved=True,
            chief_ai_approved=True,
        )
        similarity_summary = await self._similarity_summary_for_direction(
            session, timeframe=_SCALPING_SIMILARITY_TIMEFRAME, direction=signal.direction
        )
        signal_workflow = SignalWorkflow(
            trade_repository=TradeRepository(session),
            mt5_client=self._mt5,
            telegram_notifier=self._telegram,
        )
        workflow_input = SignalWorkflowInput(
            symbol_id=effective_config.symbol_id,
            market_symbol_name=effective_config.mt5_symbol,
            entry_price=signal.entry_price,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            position_size=position_size,
            execution_request=execution_request,
            strategy_name=f"{effective_config.strategy_name}{_SCALPING_STRATEGY_SUFFIX}",
            strategy_version=effective_config.strategy_version,
            telegram_chat_id=effective_config.telegram_chat_id,
            department_votes={
                "scalping_engine": {
                    "bias": "bullish" if signal.direction == "buy" else "bearish",
                    "confidence": signal.confidence,
                }
            },
            market_regime=signal.htf_trend_regime,
            similarity_summary=similarity_summary,
        )
        result = await signal_workflow.run(
            _scalping_decision(signal, department_reliability), workflow_input
        )
        logger.info(
            "scalping_signal_workflow_completed",
            executed=result.executed,
            rejection_reasons=result.rejection_reasons,
            telegram_sent=result.telegram_sent,
            reasons=signal.reasons,
        )

    async def _run_swing_analysis(
        self,
        session: AsyncSession,
        *,
        confidence_threshold_pct: float | None,
        modules: dict[str, ModuleSetting],
    ) -> SwingAnalysisOutcome:
        """Fetch fresh D1/W1 data and run the Swing Engine for this cycle.

        D1/W1 are ingested and read back through the same
        `MT5HistoricalIngestionService` + `CandleRepository` path every
        other timeframe in this platform uses, rather than bypassing
        storage (mirrors `_run_scalping_analysis`'s own M1/H1 handling).

        Args:
            session: This cycle's database session.
            confidence_threshold_pct: `RuntimeSettings.swing_confidence_threshold`
                (0-100), if the user has overridden it this cycle. None
                uses the Swing Engine's own constructed default.
            modules: The Swing engine's own assigned Strategy Builder
                profile's module settings (empty dict means every module
                stays at its default behavior).
        """
        assert self._swing_service is not None
        candle_repository = CandleRepository(session)
        ingestion = MT5HistoricalIngestionService(
            candle_repository=candle_repository, mt5_client=self._mt5
        )
        await ingestion.ingest(
            self._scan_config.symbol_id,
            mt5_symbol=self._scan_config.mt5_symbol,
            timeframe="D1",
            count=_SWING_D1_CANDLE_COUNT,
        )
        await ingestion.ingest(
            self._scan_config.symbol_id,
            mt5_symbol=self._scan_config.mt5_symbol,
            timeframe=_SWING_W1_TIMEFRAME,
            count=_SWING_W1_CANDLE_COUNT,
        )
        await ingestion.ingest(
            self._scan_config.symbol_id,
            mt5_symbol=self._scan_config.mt5_symbol,
            timeframe="H4",
            count=_SWING_H4_CANDLE_COUNT,
        )
        await ingestion.ingest(
            self._scan_config.symbol_id,
            mt5_symbol=self._scan_config.mt5_symbol,
            timeframe="M15",
            count=_SWING_M15_CANDLE_COUNT,
        )
        d1_candles = await candle_repository.list_most_recent(
            self._scan_config.symbol_id, "D1", count=_SWING_D1_CANDLE_COUNT
        )
        w1_candles = await candle_repository.list_most_recent(
            self._scan_config.symbol_id, _SWING_W1_TIMEFRAME, count=_SWING_W1_CANDLE_COUNT
        )
        h4_candles = await candle_repository.list_most_recent(
            self._scan_config.symbol_id, "H4", count=_SWING_H4_CANDLE_COUNT
        )
        m15_candles = await candle_repository.list_most_recent(
            self._scan_config.symbol_id, "M15", count=_SWING_M15_CANDLE_COUNT
        )
        tick = await self._mt5.get_symbol_tick(self._scan_config.mt5_symbol)
        enabled_agent_names = (
            {
                name
                for name in TECHNICAL_AGENT_MODULE_NAMES
                if modules.get(name, ModuleSetting()).enabled
            }
            if modules
            else None
        )
        return await self._swing_service.analyze(
            d1_candles=d1_candles,
            w1_candles=w1_candles,
            tick=tick,
            confidence_threshold=(
                confidence_threshold_pct / 100.0 if confidence_threshold_pct is not None else None
            ),
            enabled_agent_names=enabled_agent_names,
            agent_weights=profile_agent_weights(modules),
            h4_candles=h4_candles,
            m15_candles=m15_candles,
        )

    async def _execute_swing_trade(
        self,
        session: AsyncSession,
        signal: SwingSignal,
        effective_config: MarketScanConfig,
        department_reliability: dict[str, float],
    ) -> None:
        """Size and execute a Swing Engine signal via the same `SignalWorkflow`.

        Uses a distinct `strategy_name` (and therefore magic number) from
        the primary engine and the Scalping Engine so swing trades are
        always separately identifiable in MT5 and the journal, and
        dynamic risk-scaled sizing per
        `src.engines.swing_engine.position_sizing` -- "Lot size must
        NEVER increase simply because the expected movement is small."

        Args:
            session: This cycle's database session.
            signal: The Swing Engine's own signal.
            effective_config: This cycle's config, with the user's live
                Risk Mode override already applied to `risk_per_trade_pct`.
            department_reliability: This cycle's measured department
                reliability scores, for the Trade Quality Engine.
        """
        account = await self._mt5.get_account_info()
        scaled_risk_pct = compute_swing_risk_pct(
            effective_config.risk_per_trade_pct,
            SwingRiskFactors(
                confidence=signal.confidence,
                # Not yet enough swing trade history to measure a
                # realized win rate this cycle -- never a fabricated value.
                recent_win_rate=None,
            ),
        )
        position_size = compute_position_size(
            account_equity=account.equity,
            risk_per_trade_pct=scaled_risk_pct,
            entry_price=signal.entry_price,
            stop_loss_price=signal.stop_loss,
        )
        if position_size.position_size_units <= 0:
            logger.info("swing_trade_skipped", reason="zero_position_size")
            return

        # Per the "Parallel Strategy Execution" production requirement:
        # "Chief AI must evaluate total portfolio exposure before
        # approving additional positions" -- previously only the primary
        # (Intraday) engine ran this check; Swing hardcoded
        # `risk_approved=True` and never looked at the portfolio's
        # combined exposure across all three engines' trades.
        open_positions = await self._mt5.get_open_positions(symbol=effective_config.mt5_symbol)
        exposure_state = exposure_state_from_positions(open_positions, account.equity)
        exposure_breaches = check_exposure_limits(
            exposure_state, position_size.effective_risk_pct, effective_config.exposure_limits
        )
        if exposure_breaches:
            logger.info("swing_trade_skipped", reason="exposure_limit", breaches=exposure_breaches)
            return

        execution_request = ExecutionValidationRequest(
            expected_symbol=effective_config.mt5_symbol,
            order_symbol=effective_config.mt5_symbol,
            expected_account=effective_config.expected_account,
            actual_account=str(account.login),
            account_type=effective_config.account_type,
            live_trading_approved=effective_config.live_trading_approved,
            is_terminal_connected=await self._mt5.is_connected(),
            is_market_open=True,
            risk_approved=True,
            chief_ai_approved=True,
        )
        similarity_summary = await self._similarity_summary_for_direction(
            session, timeframe=_SWING_SIMILARITY_TIMEFRAME, direction=signal.direction
        )
        signal_workflow = SignalWorkflow(
            trade_repository=TradeRepository(session),
            mt5_client=self._mt5,
            telegram_notifier=self._telegram,
        )
        workflow_input = SignalWorkflowInput(
            symbol_id=effective_config.symbol_id,
            market_symbol_name=effective_config.mt5_symbol,
            entry_price=signal.entry_price,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            position_size=position_size,
            execution_request=execution_request,
            strategy_name=f"{effective_config.strategy_name}{_SWING_STRATEGY_SUFFIX}",
            strategy_version=effective_config.strategy_version,
            telegram_chat_id=effective_config.telegram_chat_id,
            department_votes={
                "swing_engine": {
                    "bias": "bullish" if signal.direction == "buy" else "bearish",
                    "confidence": signal.confidence,
                }
            },
            market_regime=signal.weekly_trend_regime,
            similarity_summary=similarity_summary,
        )
        result = await signal_workflow.run(
            _swing_decision(signal, department_reliability), workflow_input
        )
        logger.info(
            "swing_signal_workflow_completed",
            executed=result.executed,
            rejection_reasons=result.rejection_reasons,
            telegram_sent=result.telegram_sent,
            reasons=signal.reasons,
        )

    async def _fetch_shakky_candles(
        self, session: AsyncSession
    ) -> tuple[
        list[Candle], list[Candle], list[Candle], list[Candle], list[Candle], list[Candle] | None
    ]:
        """Ingest + read M5/M15/H1/H4/D1 (+ DXY) candles for Shakky this cycle.

        Every timeframe is ingested and read back through the same
        `MT5HistoricalIngestionService` + `CandleRepository` path every
        other engine in this platform uses, mirroring
        `_run_scalping_analysis`/`_run_swing_analysis`. Shared by
        `_run_shakky_analysis` (entry signal search) and
        `_manage_shakky_positions` (open-position management) so both
        use the exact same freshly-ingested data this cycle, rather than
        two independent fetches that could disagree.

        Returns:
            `(m5, m15, h1, h4, d1, dxy)` -- `dxy` is None if any of its 5
            FX components is unavailable this cycle
            (`_fetch_dxy_candles`'s own honest "no DXY data" case).
        """
        candle_repository = CandleRepository(session)
        ingestion = MT5HistoricalIngestionService(
            candle_repository=candle_repository, mt5_client=self._mt5
        )
        for timeframe, count in (
            ("M5", _SHAKKY_M5_CANDLE_COUNT),
            ("M15", _SHAKKY_M15_CANDLE_COUNT),
            ("H1", _SHAKKY_H1_CANDLE_COUNT),
            ("H4", _SHAKKY_H4_CANDLE_COUNT),
            ("D1", _SHAKKY_D1_CANDLE_COUNT),
        ):
            await ingestion.ingest(
                self._scan_config.symbol_id,
                mt5_symbol=self._scan_config.mt5_symbol,
                timeframe=timeframe,
                count=count,
            )
        m5_candles = await candle_repository.list_most_recent(
            self._scan_config.symbol_id, "M5", count=_SHAKKY_M5_CANDLE_COUNT
        )
        m15_candles = await candle_repository.list_most_recent(
            self._scan_config.symbol_id, "M15", count=_SHAKKY_M15_CANDLE_COUNT
        )
        h1_candles = await candle_repository.list_most_recent(
            self._scan_config.symbol_id, "H1", count=_SHAKKY_H1_CANDLE_COUNT
        )
        h4_candles = await candle_repository.list_most_recent(
            self._scan_config.symbol_id, "H4", count=_SHAKKY_H4_CANDLE_COUNT
        )
        d1_candles = await candle_repository.list_most_recent(
            self._scan_config.symbol_id, "D1", count=_SHAKKY_D1_CANDLE_COUNT
        )
        dxy_candles = await self._fetch_dxy_candles(session)
        return m5_candles, m15_candles, h1_candles, h4_candles, d1_candles, dxy_candles

    async def _run_shakky_analysis(
        self, session: AsyncSession
    ) -> tuple[ShakkyAnalysisOutcome, TrendConfidenceAssessment | None]:
        """Run Shakky's entry search for this cycle, plus entry-time Trend Confidence.

        Returns:
            `(outcome, trend_confidence)` -- `trend_confidence` is the
            Trend Confidence Engine's assessment for `outcome.signal`'s
            own direction (`src.engines.shakky_engine.trend_confidence`),
            None when no signal was found this cycle. Computed from the
            exact same candles the signal search itself used, so
            `Trade.entry_trend_confidence_score` always reflects the
            data that actually produced the trade.
        """
        assert self._shakky_service is not None
        (
            m5_candles,
            m15_candles,
            h1_candles,
            h4_candles,
            d1_candles,
            dxy_candles,
        ) = await self._fetch_shakky_candles(session)
        tick = await self._mt5.get_symbol_tick(self._scan_config.mt5_symbol)
        outcome = await self._shakky_service.analyze(
            m5_candles=m5_candles,
            m15_candles=m15_candles,
            h1_candles=h1_candles,
            h4_candles=h4_candles,
            d1_candles=d1_candles,
            dxy_candles=dxy_candles,
            tick=tick,
        )
        trend_confidence = (
            assess_trend_confidence(
                direction=outcome.signal.direction,
                entry_price=outcome.signal.entry_price,
                d1_candles=d1_candles,
                h4_candles=h4_candles,
                h1_candles=h1_candles,
                m15_candles=m15_candles,
                m5_candles=m5_candles,
                dxy_candles=dxy_candles,
            )
            if outcome.signal is not None
            else None
        )
        return outcome, trend_confidence

    async def _fetch_micro_scalping_candles(
        self, session: AsyncSession
    ) -> tuple[list[Candle], list[Candle], list[Candle], list[Candle] | None, list[Candle] | None]:
        """Ingest + read M1/M5/M15/H1 candles for Micro Scalping this cycle.

        Per its own narrower timeframe spec (M1/M5 primary, M15/H1
        confirmation only -- no H4/D1), mirrors `_fetch_shakky_candles`'s
        ingest-then-read pattern with its own smaller timeframe set.

        Returns:
            `(m1, m5, m15, h1, dxy)` -- `dxy` reuses `_fetch_dxy_candles`
            (already shared, not Shakky-specific).
        """
        candle_repository = CandleRepository(session)
        ingestion = MT5HistoricalIngestionService(
            candle_repository=candle_repository, mt5_client=self._mt5
        )
        for timeframe, count in (
            ("M1", _MICRO_SCALPING_M1_CANDLE_COUNT),
            ("M5", _MICRO_SCALPING_M5_CANDLE_COUNT),
            ("M15", _MICRO_SCALPING_M15_CANDLE_COUNT),
            ("H1", _MICRO_SCALPING_H1_CANDLE_COUNT),
        ):
            await ingestion.ingest(
                self._scan_config.symbol_id,
                mt5_symbol=self._scan_config.mt5_symbol,
                timeframe=timeframe,
                count=count,
            )
        m1_candles = await candle_repository.list_most_recent(
            self._scan_config.symbol_id, "M1", count=_MICRO_SCALPING_M1_CANDLE_COUNT
        )
        m5_candles = await candle_repository.list_most_recent(
            self._scan_config.symbol_id, "M5", count=_MICRO_SCALPING_M5_CANDLE_COUNT
        )
        m15_candles = await candle_repository.list_most_recent(
            self._scan_config.symbol_id, "M15", count=_MICRO_SCALPING_M15_CANDLE_COUNT
        )
        h1_candles = await candle_repository.list_most_recent(
            self._scan_config.symbol_id, "H1", count=_MICRO_SCALPING_H1_CANDLE_COUNT
        )
        dxy_candles = await self._fetch_dxy_candles(session)
        return m1_candles, m5_candles, m15_candles, h1_candles, dxy_candles

    async def _run_micro_scalping_analysis(
        self, session: AsyncSession, runtime_settings: RuntimeSettings
    ) -> MicroScalpingAnalysisOutcome:
        """Run Micro Scalping's entry search for this cycle."""
        assert self._micro_scalping_service is not None
        (
            m1_candles,
            m5_candles,
            m15_candles,
            h1_candles,
            dxy_candles,
        ) = await self._fetch_micro_scalping_candles(session)
        tick = await self._mt5.get_symbol_tick(self._scan_config.mt5_symbol)
        recent_news = await NewsArticleRepository(session).list_high_importance(
            limit=_MICRO_SCALPING_NEWS_LOOKBACK_LIMIT
        )
        min_confidence = (
            _demo_learning_discount(
                runtime_settings.micro_scalping_min_confidence, runtime_settings
            )
            if runtime_settings.micro_scalping_min_confidence is not None
            else _MICRO_SCALPING_DEFAULT_MIN_CONFIDENCE
        )
        max_spread_points = (
            runtime_settings.micro_scalping_max_spread_points
            if runtime_settings.micro_scalping_max_spread_points is not None
            else _MICRO_SCALPING_DEFAULT_MAX_SPREAD_POINTS
        )
        return await self._micro_scalping_service.analyze(
            m1_candles=m1_candles,
            m5_candles=m5_candles,
            m15_candles=m15_candles,
            h1_candles=h1_candles,
            dxy_candles=dxy_candles,
            tick=tick,
            recent_high_importance_news=recent_news,
            min_confidence=min_confidence,
            max_spread_points=max_spread_points,
        )

    async def _execute_micro_scalping_trade(
        self,
        session: AsyncSession,
        signal: MicroScalpingSignal,
        effective_config: MarketScanConfig,
        runtime_settings: RuntimeSettings,
        trend_confidence_score: float | None,
    ) -> None:
        """Size and execute a Micro Scalping signal directly, bypassing `SignalWorkflow`.

        Per this engine's own spec ("Do NOT invent a new strategy...
        the difference is only trade management"): same direct-
        execution shape as `_execute_shakky_trade` (no Chief AI/Trade
        Quality Engine call -- Shakky's own spec this engine inherits
        forbids both), with its own lot-sizing mode ("auto" via
        `compute_position_size`, or "manual" via
        `compute_fixed_lot_position_size`, per
        `RuntimeSettings.micro_scalping_lot_mode`) and no broker-side
        `take_profit` -- exit is managed entirely by
        `_manage_micro_scalping_positions` every cycle instead.

        Args:
            session: This cycle's database session.
            signal: The Micro Scalping Engine's own signal.
            effective_config: This cycle's config.
            runtime_settings: This cycle's `RuntimeSettings` row, for
                the lot-sizing mode.
            trend_confidence_score: The Trend Confidence Engine's score
                at entry, persisted onto `Trade.entry_trend_confidence_score`
                for `_manage_micro_scalping_positions`'s own later reads.
        """
        account = await self._mt5.get_account_info()
        if runtime_settings.micro_scalping_lot_mode == "manual":
            position_size = compute_fixed_lot_position_size(
                fixed_lot_size=(
                    runtime_settings.micro_scalping_fixed_lot_size
                    or _MICRO_SCALPING_DEFAULT_FIXED_LOT_SIZE
                ),
                account_equity=account.equity,
                entry_price=signal.entry_price,
                stop_loss_price=signal.stop_loss,
            )
        else:
            position_size = compute_position_size(
                account_equity=account.equity,
                risk_per_trade_pct=effective_config.risk_per_trade_pct,
                entry_price=signal.entry_price,
                stop_loss_price=signal.stop_loss,
            )
        if position_size.position_size_units <= 0:
            logger.info("micro_scalping_trade_skipped", reason="zero_position_size")
            return

        open_positions = await self._mt5.get_open_positions(symbol=effective_config.mt5_symbol)
        exposure_state = exposure_state_from_positions(open_positions, account.equity)
        exposure_breaches = check_exposure_limits(
            exposure_state, position_size.effective_risk_pct, effective_config.exposure_limits
        )
        if exposure_breaches:
            logger.info(
                "micro_scalping_trade_skipped", reason="exposure_limit", breaches=exposure_breaches
            )
            return

        execution_request = ExecutionValidationRequest(
            expected_symbol=effective_config.mt5_symbol,
            order_symbol=effective_config.mt5_symbol,
            expected_account=effective_config.expected_account,
            actual_account=str(account.login),
            account_type=effective_config.account_type,
            live_trading_approved=effective_config.live_trading_approved,
            is_terminal_connected=await self._mt5.is_connected(),
            is_market_open=True,
            risk_approved=True,
            chief_ai_approved=True,
        )
        execution_check = validate_execution(execution_request)
        if not execution_check.approved:
            logger.info("micro_scalping_trade_skipped", reasons=execution_check.rejection_reasons)
            return

        direction = signal.direction
        trade_repository = TradeRepository(session)
        trade = await trade_repository.add(
            Trade(
                symbol_id=effective_config.symbol_id,
                direction=direction,
                status="pending",
                volume=position_size.position_size_units,
                entry_price=signal.entry_price,
                stop_loss=signal.stop_loss,
                initial_stop_loss=signal.stop_loss,
                take_profit=None,
                magic_number=self._micro_scalping_magic_number,
                strategy_version=effective_config.strategy_version,
                department_votes={
                    "micro_scalping_engine": {
                        "bias": "bullish" if direction == "buy" else "bearish",
                        "dominant_family": signal.dominant_family,
                        "confirmation_count": len(signal.confirmations),
                    }
                },
                reasons=signal.reasons,
                entry_trend_confidence_score=trend_confidence_score,
            )
        )

        order_result = await self._mt5.place_order(
            OrderRequest(
                symbol=effective_config.mt5_symbol,
                order_type=direction,
                volume=trade.volume,
                stop_loss=trade.stop_loss,
                take_profit=None,
                magic_number=self._micro_scalping_magic_number,
                comment=_micro_scalping_order_comment(effective_config.strategy_name, trade.id),
            )
        )

        if not order_result.success:
            trade.status = "rejected"
            trade.error_message = order_result.error_message
            await trade_repository.add(trade)
            logger.info("micro_scalping_trade_rejected", error=order_result.error_message)
            return

        trade.status = "open"
        trade.broker_ticket = order_result.broker_ticket
        trade.opened_at = datetime.now(UTC)
        await trade_repository.add(trade)

        message = (
            "⚡ Микро-скальп -- вход\n"
            f"Инструмент: {effective_config.mt5_symbol}\n"
            f"Направление: {'BUY' if direction == 'buy' else 'SELL'}\n"
            f"Вход: {signal.entry_price:.2f}\n"
            f"Стоп: {signal.stop_loss:.2f}\n"
            f"Логика: {signal.dominant_family}\n"
            f"ID сделки: {trade.id}"
        )
        telegram_sent = await self._telegram.send_message(
            effective_config.telegram_chat_id, message
        )
        logger.info(
            "micro_scalping_trade_executed",
            broker_ticket=trade.broker_ticket,
            telegram_sent=telegram_sent,
            reasons=signal.reasons,
        )

    async def _manage_micro_scalping_positions(self, session: AsyncSession) -> None:
        """Dynamic profit-target/trailing exit management for open Micro Scalping trades.

        Per the engine's own spec ("minimum profit target ~+1 USDT...
        trailing stop instead of closing if momentum remains
        exceptionally strong... never hold for hours"): every cycle,
        each open Micro Scalping position is re-assessed with a fresh
        `evaluate_micro_scalping_exit` read and acted on immediately --
        unlike Shakky's own Dynamic TP (which only ever extends/tightens
        a broker-side take profit), this engine never sets one, so exit
        is entirely this loop's own responsibility. Runs independently
        of `_run_position_monitoring` (generic break-even/trailing,
        applied uniformly to every strategy including this one) -- this
        step only ever trails the stop further in the position's own
        favor or closes outright, the same non-conflicting invariant
        `_manage_shakky_positions` documents for its own Dynamic TP.
        """
        if self._micro_scalping_service is None:
            return
        runtime_settings = await RuntimeSettingsRepository(session).get_or_create_default()
        if not runtime_settings.micro_scalping_enabled:
            return

        positions = await self._mt5.get_open_positions(
            symbol=self._scan_config.mt5_symbol, magic_number=self._micro_scalping_magic_number
        )
        if not positions:
            return

        (
            m1_candles,
            m5_candles,
            m15_candles,
            h1_candles,
            dxy_candles,
        ) = await self._fetch_micro_scalping_candles(session)
        atr = average_true_range(m5_candles, period=_MICRO_SCALPING_ATR_PERIOD)
        trade_repository = TradeRepository(session)
        # "Dynamic Profit Target" (whether extending beyond the flat
        # target is allowed at all) gates the same end-user-visible
        # behavior as "Trailing Stop" (the only extension mechanism this
        # engine implements) -- both must be enabled to ever trail
        # rather than close flat, per each toggle's own docstring on
        # `RuntimeSettings`.
        trailing_stop_enabled = (
            runtime_settings.micro_scalping_dynamic_profit_target_enabled
            and runtime_settings.micro_scalping_trailing_stop_enabled
        )
        max_holding_minutes = (
            runtime_settings.micro_scalping_max_holding_minutes
            if runtime_settings.micro_scalping_max_holding_minutes is not None
            else _MICRO_SCALPING_DEFAULT_MAX_HOLDING_MINUTES
        )

        for position in positions:
            trade = await trade_repository.get_by_broker_ticket(position.ticket)
            if trade is None or trade.entry_price is None or trade.opened_at is None:
                continue

            self._update_micro_scalping_excursion(trade, position)

            momentum_result = micro_scalping_check_momentum(m1_candles)
            trend_confidence = assess_trend_confidence(
                direction=position.direction,
                entry_price=position.current_price,
                d1_candles=None,
                h4_candles=None,
                h1_candles=h1_candles,
                m15_candles=m15_candles,
                m5_candles=m5_candles,
                dxy_candles=dxy_candles,
            )
            momentum_still_strong = momentum_result.passed and trend_confidence.level in (
                "strong",
                "exceptional",
            )
            holding_minutes = (datetime.now(UTC) - trade.opened_at).total_seconds() / 60.0

            decision = evaluate_micro_scalping_exit(
                direction=position.direction,
                floating_profit_usd=position.profit,
                min_profit_target_usd=_MICRO_SCALPING_DEFAULT_MIN_PROFIT_TARGET_USD,
                momentum_still_strong=momentum_still_strong,
                current_price=position.current_price,
                current_stop_loss=position.stop_loss,
                atr=atr if atr is not None else abs(position.current_price - position.stop_loss),
                holding_minutes=holding_minutes,
                max_holding_minutes=max_holding_minutes,
                trailing_stop_enabled=trailing_stop_enabled,
            )
            await self._apply_micro_scalping_exit_decision(
                trade=trade, position=position, decision=decision, holding_minutes=holding_minutes
            )
            await trade_repository.add(trade)

    def _update_micro_scalping_excursion(self, trade: Trade, position: OpenPosition) -> None:
        """Update `Trade.max_favorable_excursion`/`max_adverse_excursion` in place.

        Same incremental tracking as `_update_shakky_excursion` -- these
        are generic `Trade` columns, not Shakky-specific, reused here so
        the future learning phase has the same MFE/MAE basis for every
        strategy.
        """
        assert trade.entry_price is not None
        favorable = (
            position.current_price - trade.entry_price
            if position.direction == "buy"
            else trade.entry_price - position.current_price
        )
        trade.max_favorable_excursion = max(trade.max_favorable_excursion or 0.0, favorable)
        trade.max_adverse_excursion = max(trade.max_adverse_excursion or 0.0, -favorable)

    async def _apply_micro_scalping_exit_decision(
        self,
        *,
        trade: Trade,
        position: OpenPosition,
        decision: MicroScalpingExitDecision,
        holding_minutes: float,
    ) -> None:
        if decision.action == "hold":
            return

        if decision.action == "trail" and decision.new_stop_loss is not None:
            modify_result = await self._mt5.modify_order(
                position.ticket, stop_loss=decision.new_stop_loss
            )
            if not modify_result.success:
                logger.warning(
                    "micro_scalping_trail_failed",
                    ticket=position.ticket,
                    error=modify_result.error_message,
                )
                return
            trade.stop_loss = decision.new_stop_loss
            logger.info(
                "micro_scalping_stop_trailed",
                ticket=position.ticket,
                new_stop_loss=decision.new_stop_loss,
                reasons=decision.reasons,
            )
            return

        # "close_full" -- reuses `PositionMonitor._reconcile_closed_positions`'s
        # existing broker-vs-journal reconciliation (including its
        # automatic post-mortem) on the next `_run_position_monitoring`
        # cycle rather than duplicating that logic here; this only
        # issues the close order and lets that generic mechanism catch it.
        close_result = await self._mt5.close_position(position.ticket)
        if not close_result.success:
            logger.warning(
                "micro_scalping_close_failed",
                ticket=position.ticket,
                error=close_result.error_message,
            )
            return
        logger.info(
            "micro_scalping_position_closed",
            ticket=position.ticket,
            reasons=decision.reasons,
        )
        await self._notify_micro_scalping_close(trade, position, holding_minutes=holding_minutes)

    async def _notify_micro_scalping_close(
        self, trade: Trade, position: OpenPosition, *, holding_minutes: float
    ) -> None:
        """Send the user's exact specified Micro Scalping close-format Telegram message.

        Never raises: a notification failure must not undo an already-
        succeeded broker close (same guard as `_notify_shakky_position_event`).
        The three "✅" reasons are always true for any executed Micro
        Scalping trade -- every one of `check_momentum`/Shakky's own
        signal/`check_liquidity` is a hard entry gate this trade already
        passed, never a fabricated post-hoc justification.
        """
        total_seconds = max(int(holding_minutes * 60), 0)
        minutes, seconds = divmod(total_seconds, 60)
        message = (
            "⚡ Микро-скальп\n"
            f"{'🟢 BUY' if position.direction == 'buy' else '🔴 SELL'} "
            f"{self._scan_config.mt5_symbol}\n"
            f"💰 Прибыль: {'+' if position.profit >= 0 else ''}{position.profit:.2f}$\n"
            f"⏱ Время сделки: {minutes} мин {seconds} сек\n"
            "📊 Причина:\n"
            "✅ Импульс\n"
            "✅ Подтверждение Shakky\n"
            "✅ Высокая ликвидность"
        )
        try:
            await self._telegram.send_message(self._scan_config.telegram_chat_id, message)
        except Exception:
            logger.exception("micro_scalping_close_notification_failed", ticket=position.ticket)

    async def _fetch_dxy_candles(self, session: AsyncSession) -> list[Candle] | None:
        """Build synthetic DXY M5 candles from the 5 ingested FX majors this cycle.

        Per Shakky's one explicit exception to "must not use the
        Correlation Engine" ("except DXY"): DXY has no direct MT5 symbol
        on this broker, so this computes the same disclosed ICE Dollar
        Index proxy formula `src.engines.correlation_engine.analysis`
        uses (`_SHAKKY_DXY_PROXY_WEIGHTS`), applied to full OHLC instead
        of just closes, duplicated locally rather than importing that
        forbidden package. These bars are synthetic and in-memory only --
        never persisted to `candles`/`correlated_prices`.

        Returns:
            None if any of the 5 required FX components is unavailable or
            their bars are not timestamp-aligned this cycle -- an honest
            "no DXY data," never a fabricated or mismatched series. The
            Intermarket confirmation family already treats `None` as
            "skip this family" (`collect_confirmations`).
        """
        instrument_repository = CorrelatedInstrumentRepository(session)
        price_repository = CorrelatedPriceRepository(session)
        ingestion = CorrelatedInstrumentIngestionService(
            price_repository=price_repository, mt5_client=self._mt5
        )
        component_prices: dict[str, list[CorrelatedPrice]] = {}
        for name in _SHAKKY_DXY_PROXY_WEIGHTS:
            instrument = await instrument_repository.get_by_name(name)
            if instrument is None or instrument.mt5_symbol is None:
                return None
            try:
                await ingestion.ingest(
                    instrument.id,
                    mt5_symbol=instrument.mt5_symbol,
                    timeframe="M5",
                    count=_SHAKKY_DXY_CANDLE_COUNT,
                )
            except Exception:
                logger.exception("shakky_dxy_component_refresh_failed", instrument=name)
                return None
            prices = await price_repository.list_most_recent(
                instrument.id, "M5", count=_SHAKKY_DXY_CANDLE_COUNT
            )
            if len(prices) < _SHAKKY_DXY_CANDLE_COUNT:
                return None
            component_prices[name] = prices

        timestamps = [price.timestamp for price in component_prices["EURUSD"]]
        if any(
            [price.timestamp for price in prices] != timestamps
            for prices in component_prices.values()
        ):
            return None

        dxy_candles: list[Candle] = []
        for index, timestamp in enumerate(timestamps):
            bar = {
                field_name: sum(
                    _SHAKKY_DXY_PROXY_WEIGHTS[name]
                    * getattr(component_prices[name][index], field_name)
                    for name in _SHAKKY_DXY_PROXY_WEIGHTS
                )
                for field_name in ("open", "high", "low", "close")
            }
            dxy_candles.append(
                Candle(
                    symbol_id=self._scan_config.symbol_id,
                    timeframe="M5",
                    timestamp=timestamp,
                    open=bar["open"],
                    # Mixed-sign proxy weights mean a per-component
                    # high >= low does not guarantee the weighted sums
                    # keep that ordering -- swap defensively rather than
                    # ever hand a downstream ATR/wick calculation an
                    # inverted bar.
                    high=max(bar["high"], bar["low"]),
                    low=min(bar["high"], bar["low"]),
                    close=bar["close"],
                    volume=0.0,
                    source=_SHAKKY_DXY_PROXY_SOURCE,
                )
            )
        return dxy_candles

    async def _execute_shakky_trade(
        self,
        session: AsyncSession,
        signal: ShakkySignal,
        effective_config: MarketScanConfig,
        trend_confidence: TrendConfidenceAssessment | None,
    ) -> None:
        """Size and execute a Shakky signal directly, bypassing `SignalWorkflow`.

        Per Shakky's own spec ("must NOT use Chief AI decision logic
        [or] the Trade Quality Engine"): `SignalWorkflow.run()` calls
        `src.engines.chief_ai.scenarios.build_scenario_plan` and expects
        a `ChiefAIDecision` carrying a Trade Quality Engine score, so it
        cannot be reused here even in the shape-adapter way
        `_scalping_decision`/`_swing_decision` do. This journals and
        places the order directly instead, using the same `Trade`
        fields/`OrderRequest`/`validate_execution` shape --
        `quality_score`/`risk_score`/`confidence_pct`/`market_regime`/
        `scenario_plan` stay honestly `None` rather than fabricated.

        `trend_confidence` (from `_run_shakky_analysis`, same cycle) is
        persisted onto `Trade.entry_trend_confidence_score` -- the basis
        `exit_management`/`position_scaling` use later to decide whether
        this specific trade is eligible for Dynamic TP/Scaling.

        Fixed lot sizing only (`compute_fixed_lot_position_size`) per
        "Minimum lot: 0.01" -- Shakky has no confidence score to scale by.

        Args:
            session: This cycle's database session.
            signal: The Shakky Engine's own signal.
            effective_config: This cycle's config.
        """
        account = await self._mt5.get_account_info()
        position_size = compute_fixed_lot_position_size(
            fixed_lot_size=_SHAKKY_FIXED_LOT_SIZE,
            account_equity=account.equity,
            entry_price=signal.entry_price,
            stop_loss_price=signal.stop_loss,
        )

        open_positions = await self._mt5.get_open_positions(symbol=effective_config.mt5_symbol)
        exposure_state = exposure_state_from_positions(open_positions, account.equity)
        exposure_breaches = check_exposure_limits(
            exposure_state, position_size.effective_risk_pct, effective_config.exposure_limits
        )
        if exposure_breaches:
            logger.info("shakky_trade_skipped", reason="exposure_limit", breaches=exposure_breaches)
            return

        execution_request = ExecutionValidationRequest(
            expected_symbol=effective_config.mt5_symbol,
            order_symbol=effective_config.mt5_symbol,
            expected_account=effective_config.expected_account,
            actual_account=str(account.login),
            account_type=effective_config.account_type,
            live_trading_approved=effective_config.live_trading_approved,
            is_terminal_connected=await self._mt5.is_connected(),
            is_market_open=True,
            risk_approved=True,
            chief_ai_approved=True,
        )
        execution_check = validate_execution(execution_request)
        if not execution_check.approved:
            logger.info("shakky_trade_skipped", reasons=execution_check.rejection_reasons)
            return

        direction = signal.direction
        trade_repository = TradeRepository(session)
        trade = await trade_repository.add(
            Trade(
                symbol_id=effective_config.symbol_id,
                direction=direction,
                status="pending",
                volume=position_size.position_size_units,
                entry_price=signal.entry_price,
                stop_loss=signal.stop_loss,
                initial_stop_loss=signal.stop_loss,
                take_profit=signal.take_profit,
                magic_number=self._shakky_magic_number,
                strategy_version=effective_config.strategy_version,
                department_votes={
                    "shakky_engine": {
                        "bias": "bullish" if direction == "buy" else "bearish",
                        "dominant_family": signal.dominant_family,
                        "confirmation_count": len(signal.confirmations),
                    }
                },
                reasons=signal.reasons,
                entry_trend_confidence_score=(
                    trend_confidence.score if trend_confidence is not None else None
                ),
            )
        )

        order_result = await self._mt5.place_order(
            OrderRequest(
                symbol=effective_config.mt5_symbol,
                order_type=direction,
                volume=trade.volume,
                stop_loss=trade.stop_loss,
                take_profit=trade.take_profit,
                magic_number=self._shakky_magic_number,
                comment=_shakky_order_comment(effective_config.strategy_name, trade.id),
            )
        )

        if not order_result.success:
            trade.status = "rejected"
            trade.error_message = order_result.error_message
            await trade_repository.add(trade)
            logger.info("shakky_trade_rejected", error=order_result.error_message)
            return

        trade.status = "open"
        trade.broker_ticket = order_result.broker_ticket
        trade.opened_at = datetime.now(UTC)
        await trade_repository.add(trade)

        message = (
            "🅼🅵 Classic M5 Strategy (Shakky)\n"
            f"Инструмент: {effective_config.mt5_symbol}\n"
            f"Направление: {'BUY' if direction == 'buy' else 'SELL'}\n"
            f"Вход: {signal.entry_price:.2f}\n"
            f"Стоп: {signal.stop_loss:.2f}\n"
            f"Цель: {signal.take_profit:.2f}\n"
            f"Логика: {signal.dominant_family}\n"
            f"Подтверждений: {len(signal.confirmations)}\n"
            f"ID сделки: {trade.id}"
        )
        telegram_sent = await self._telegram.send_message(
            effective_config.telegram_chat_id, message
        )
        logger.info(
            "shakky_trade_executed",
            broker_ticket=trade.broker_ticket,
            telegram_sent=telegram_sent,
            reasons=signal.reasons,
        )
