"""Scalping Engine orchestrator.

Per this platform's operating instructions: a dedicated, institutional-
grade engine "completely independent from the Swing and Intraday
Engines" (i.e. `src.workflows.market_update.pipeline.MarketScanner`,
which this platform currently runs on a single configurable timeframe —
see that module's own docstring for the honest scope of "intraday" vs
"swing" in this codebase today). Operates on M1, confirms the higher-
timeframe trend, and only signals when microstructure + order flow
evidence clears a confidence threshold — "The objective is not to
maximize trade count. The objective is to maximize long-term risk-
adjusted returns."

Reuses already-built engines rather than duplicating them
(CODING_STANDARDS.md): `src.agents.technical.volatility.average_true_range`
for stop/target sizing, `src.engines.historical_engine.regime_detection`
for higher-timeframe trend confirmation, `src.engines.order_flow_engine`
for order flow confirmation, and
`src.engines.risk_engine.position_sizing.compute_position_size` (via
`src.engines.scalping_engine.position_sizing`) for dynamic sizing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from src.agents.technical.volatility import average_true_range
from src.core.agents.confluence import CombinedVote
from src.core.execution.mt5_client import SymbolTick
from src.engines.chief_ai.multi_timeframe import (
    combine_timeframe_confirmations,
    confirm_timeframe,
)
from src.engines.historical_engine.regime_detection import classify_regime
from src.engines.order_flow_engine.service import OrderFlowAnalysisService, OrderFlowResult
from src.engines.scalping_engine.microstructure import (
    detect_breakout_failure,
    detect_micro_pullback,
    detect_momentum_burst,
)
from src.models.candle import Candle

_DEFAULT_ATR_PERIOD = 14
_DEFAULT_STOP_ATR_MULTIPLE = 1.0
_DEFAULT_REWARD_RISK_RATIO = 1.2
_DEFAULT_CONFIDENCE_THRESHOLD = 0.6
_MIN_HTF_CANDLES = 20
_MIN_M1_CANDLES = 20
# Trading against a strong higher-timeframe trend is allowed, but only
# when the rest of the evidence is unusually strong — this discount makes
# that bar meaningfully higher rather than fabricating a hard block.
_COUNTER_TREND_CONFIDENCE_DISCOUNT = 0.5

_TREND_REGIMES: frozenset[str] = frozenset({"bull_trend", "bear_trend"})


@dataclass(frozen=True, slots=True)
class ScalpingAnalysisOutcome:
    """The Scalping Engine's outcome for one cycle -- always returned.

    Per the "Why No Trade" production requirement: every strategy must
    show "Trade not opened. Reasons. Trade Quality Score. Confidence.
    Missing confirmations" -- even a cycle with no signal at all must
    surface why, not silently return nothing.

    Attributes:
        signal: The actionable signal, if confidence cleared the
            threshold this cycle. None means no trade this cycle.
        direction: The best directional read this cycle, if any evidence
            was measured at all (even below threshold). None when there
            was no microstructure signal to measure a direction from --
            never a fabricated direction.
        confidence_pct: The best measured confidence this cycle, in
            [0.0, 100.0]. 0.0 when no evidence was measured at all.
        reasons: The signal's own contributing factors when actionable,
            or the specific reason(s) this cycle did not qualify.
    """

    signal: ScalpingSignal | None
    direction: Literal["buy", "sell"] | None = None
    confidence_pct: float = 0.0
    reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ScalpingSignal:
    """A single actionable scalping opportunity.

    Attributes:
        direction: "buy" or "sell".
        confidence: Overall confidence in [0.0, 1.0], already discounted
            if the signal runs counter to the higher-timeframe trend.
        entry_price: Planned entry price (current tick).
        stop_loss: Protective stop, `_DEFAULT_STOP_ATR_MULTIPLE` times M1
            ATR from entry.
        take_profit: Target price at `_DEFAULT_REWARD_RISK_RATIO` times the
            stop distance.
        htf_trend_regime: The higher-timeframe regime this signal was
            confirmed (or discounted) against.
        reasons: Every contributing microstructure/order-flow/correlation factor.
        is_counter_trend: Whether this signal opposes `htf_trend_regime`.
    """

    direction: Literal["buy", "sell"]
    confidence: float
    entry_price: float
    stop_loss: float
    take_profit: float
    htf_trend_regime: str | None
    reasons: list[str] = field(default_factory=list)
    is_counter_trend: bool = False


class ScalpingAnalysisService:
    """Runs the Scalping Engine's full M1 analysis cycle."""

    def __init__(
        self,
        *,
        order_flow_service: OrderFlowAnalysisService,
        confidence_threshold: float = _DEFAULT_CONFIDENCE_THRESHOLD,
        atr_period: int = _DEFAULT_ATR_PERIOD,
        stop_atr_multiple: float = _DEFAULT_STOP_ATR_MULTIPLE,
        reward_risk_ratio: float = _DEFAULT_REWARD_RISK_RATIO,
    ) -> None:
        """Initialize the service (constructor injection).

        Args:
            order_flow_service: Shared Order Flow Engine instance (must be
                constructed once and reused across cycles — see that
                service's own docstring).
            confidence_threshold: Minimum confidence to produce a signal;
                below this, `analyze()` returns None (skip the trade).
            atr_period: M1 bars to average True Range over.
            stop_atr_multiple: Stop distance as a multiple of M1 ATR.
            reward_risk_ratio: Target distance as a multiple of the stop distance.
        """
        self._order_flow = order_flow_service
        self._confidence_threshold = confidence_threshold
        self._atr_period = atr_period
        self._stop_atr_multiple = stop_atr_multiple
        self._reward_risk_ratio = reward_risk_ratio

    async def analyze(
        self,
        *,
        mt5_symbol: str,
        m1_candles: list[Candle],
        htf_candles: list[Candle],
        tick: SymbolTick,
        correlation_vote: CombinedVote | None = None,
        confidence_threshold: float | None = None,
        m15_candles: list[Candle] | None = None,
        m5_candles: list[Candle] | None = None,
    ) -> ScalpingAnalysisOutcome:
        """Run one full Scalping Engine analysis cycle.

        Args:
            mt5_symbol: Broker symbol name.
            m1_candles: Recent M1 candles, ordered by timestamp ascending.
            htf_candles: Recent higher-timeframe candles (M15/H1/H4) for
                trend confirmation, ordered by timestamp ascending.
            tick: The current bid/ask quote.
            correlation_vote: The primary Market Update Workflow cycle's
                own "correlation" department vote, if available, reused
                here rather than re-running correlation analysis at M1
                scale (see this module's docstring).
            confidence_threshold: Per-call override of the constructor's
                own `confidence_threshold`, so the "Independent Confidence
                Thresholds" production requirement's live per-strategy
                setting (`RuntimeSettings.scalping_confidence_threshold`)
                takes effect every cycle without reconstructing this
                long-lived service. None uses the constructor default.
            m15_candles: Per the "Complete Multi-Timeframe Analysis"
                production requirement's own Scalping role ("Primary: H1 +
                M15"): an additional confirmation layer alongside
                `htf_candles` (H1). None skips this check entirely
                (backward compatible).
            m5_candles: Per the same requirement's Scalping "Confirmation:
                M5" role: a short-term confirmation layer between the
                higher-timeframe read and the M1 entry signal. None skips
                this check entirely.

        Returns:
            A `ScalpingAnalysisOutcome`, always -- `.signal` is None when
            there is no microstructure signal, too little history, or
            confidence falls below the effective confidence threshold —
            never a fabricated trade, but never a silently discarded
            "why not" either.
        """
        effective_threshold = (
            confidence_threshold if confidence_threshold is not None else self._confidence_threshold
        )
        if len(m1_candles) < _MIN_M1_CANDLES:
            return ScalpingAnalysisOutcome(signal=None, reasons=["insufficient_m1_history"])

        signals: list[tuple[Literal["buy", "sell"], float, str]] = []

        burst = detect_momentum_burst(m1_candles, atr_period=self._atr_period)
        if burst is not None:
            direction: Literal["buy", "sell"] = "buy" if burst.direction == "bullish" else "sell"
            signals.append(
                (
                    direction,
                    min(1.0, burst.atr_multiple / 3),
                    f"momentum_burst:{burst.move_pct:+.3f}%",
                )
            )

        failure = detect_breakout_failure(m1_candles)
        if failure is not None:
            direction = "buy" if failure.direction == "bullish" else "sell"
            signals.append((direction, 0.6, f"breakout_failure_at:{failure.broken_level:.2f}"))

        pullback = detect_micro_pullback(m1_candles, atr_period=self._atr_period)
        if pullback is not None:
            direction = "buy" if pullback.direction == "bullish" else "sell"
            signals.append((direction, 1.0 - pullback.retrace_pct, "micro_pullback_continuation"))

        if not signals:
            return ScalpingAnalysisOutcome(signal=None, reasons=["no_microstructure_signal"])

        order_flow_result = await self._order_flow.analyze(mt5_symbol, m1_candles)
        reasons = [reason for _, _, reason in signals]
        direction, confidence = _combine_signals(signals, order_flow_result, correlation_vote)
        if order_flow_result.confidence > 0:
            reasons.append(f"order_flow[{order_flow_result.source}]")
        if correlation_vote is not None:
            reasons.append("correlation_confirmation")

        htf_regime = (
            classify_regime(htf_candles).regime if len(htf_candles) >= _MIN_HTF_CANDLES else None
        )
        is_counter_trend = htf_regime in _TREND_REGIMES and (htf_regime == "bull_trend") != (
            direction == "buy"
        )
        if is_counter_trend:
            confidence *= _COUNTER_TREND_CONFIDENCE_DISCOUNT
            reasons.append(f"counter_trend_discount_applied_against:{htf_regime}")

        # Per the "Complete Multi-Timeframe Analysis" production
        # requirement: M15 (alongside H1, both "Primary") and M5
        # ("Confirmation") each independently confirm or discount this
        # candidate direction -- reuses the same discount convention as
        # the H1 check above, generalized across additional timeframes.
        additional_confirmations = []
        if m15_candles is not None:
            additional_confirmations.append(confirm_timeframe("M15", m15_candles, direction))
        if m5_candles is not None:
            additional_confirmations.append(confirm_timeframe("M5", m5_candles, direction))
        if additional_confirmations:
            mtf_result = combine_timeframe_confirmations(
                additional_confirmations,
                discount_per_disagreement=_COUNTER_TREND_CONFIDENCE_DISCOUNT,
            )
            confidence *= mtf_result.confidence_multiplier
            reasons.extend(mtf_result.reasons)

        if confidence < effective_threshold:
            reasons.append(f"confidence_below_threshold:{confidence:.2f}<{effective_threshold:.2f}")
            return ScalpingAnalysisOutcome(
                signal=None,
                direction=direction,
                confidence_pct=min(1.0, confidence) * 100,
                reasons=reasons,
            )

        atr = average_true_range(m1_candles, period=self._atr_period)
        if atr is None or atr <= 0:
            reasons.append("undefined_atr")
            return ScalpingAnalysisOutcome(
                signal=None,
                direction=direction,
                confidence_pct=min(1.0, confidence) * 100,
                reasons=reasons,
            )

        entry_price = tick.ask if direction == "buy" else tick.bid
        stop_distance = atr * self._stop_atr_multiple
        target_distance = stop_distance * self._reward_risk_ratio
        stop_loss = (
            entry_price - stop_distance if direction == "buy" else entry_price + stop_distance
        )
        take_profit = (
            entry_price + target_distance if direction == "buy" else entry_price - target_distance
        )

        signal = ScalpingSignal(
            direction=direction,
            confidence=min(1.0, confidence),
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            htf_trend_regime=htf_regime,
            reasons=reasons,
            is_counter_trend=is_counter_trend,
        )
        return ScalpingAnalysisOutcome(
            signal=signal,
            direction=direction,
            confidence_pct=signal.confidence * 100,
            reasons=reasons,
        )


def _combine_signals(
    signals: list[tuple[Literal["buy", "sell"], float, str]],
    order_flow_result: OrderFlowResult,
    correlation_vote: CombinedVote | None,
) -> tuple[Literal["buy", "sell"], float]:
    """Combine microstructure signals with order flow/correlation confirmation.

    Returns the majority-weighted direction and a confidence-weighted
    agreement score in [0.0, 1.0].
    """
    buy_weight = sum(weight for direction, weight, _ in signals if direction == "buy")
    sell_weight = sum(weight for direction, weight, _ in signals if direction == "sell")

    buy_weight += order_flow_result.bullish_probability * order_flow_result.confidence
    sell_weight += order_flow_result.bearish_probability * order_flow_result.confidence

    if correlation_vote is not None:
        buy_weight += correlation_vote.bullish_probability * correlation_vote.confidence
        sell_weight += correlation_vote.bearish_probability * correlation_vote.confidence

    total_weight = buy_weight + sell_weight
    if total_weight <= 0:
        return "buy", 0.0

    direction: Literal["buy", "sell"] = "buy" if buy_weight >= sell_weight else "sell"
    winning_weight = buy_weight if direction == "buy" else sell_weight
    confidence = winning_weight / total_weight
    return direction, confidence
