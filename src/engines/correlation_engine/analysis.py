"""Market Correlation Engine orchestrator.

Aligns XAUUSD price history against every enabled `CorrelatedInstrument`
and computes rolling correlation, lead-lag, volatility transmission,
cointegration and regime-dependent correlation for each — then ranks
instruments by a dynamic (recomputed every cycle, never fixed) feature
importance score. Per this platform's operating instructions: "These
signals must never force a trade. They only increase or decrease
confidence" — nothing here returns a trade direction or decision, only
descriptive statistics for `src.workflows.market_update.pipeline` (or a
future correlation-aware department vote) to consume.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from src.engines.correlation_engine.statistics import (
    CointegrationResult,
    LeadLagResult,
    RollingCorrelationResult,
    cointegration_test,
    lead_lag_correlation,
    log_returns,
    rolling_correlation,
    volatility_transmission,
)
from src.engines.historical_engine.regime_detection import classify_regime
from src.models.candle import Candle
from src.models.correlated_instrument import CorrelatedInstrument
from src.models.correlated_price import CorrelatedPrice
from src.repositories.candle_repository import CandleRepository
from src.repositories.correlated_instrument_repository import CorrelatedInstrumentRepository
from src.repositories.correlated_price_repository import CorrelatedPriceRepository

_REGIME_WINDOW_SIZE = 20
_COINTEGRATION_BONUS = 0.1
_SAMPLE_CONFIDENCE_NORMALIZER = 200.0
_BASE_COINTEGRATION_SIGNIFICANCE_LEVEL = 0.05

# ICE US Dollar Index formula weights, renormalized across the 5 majors
# this broker actually offers (SEK, the 6th official component, has no
# direct MT5 symbol here) — a disclosed, standard public formula applied
# to live cross rates, not a claim of replicating the exact exchange-
# traded index.
_DXY_PROXY_WEIGHTS: dict[str, float] = {
    "EURUSD": -0.6316,
    "USDJPY": 0.1489,
    "GBPUSD": -0.1303,
    "USDCAD": 0.0997,
    "USDCHF": 0.0395,
}


@dataclass(frozen=True, slots=True)
class InstrumentCorrelationReport:
    """Every correlation measurement computed for one correlated instrument.

    Attributes:
        instrument_name: The `CorrelatedInstrument.name`.
        category: The `CorrelatedInstrument.category`.
        rolling_correlation: Contemporaneous Pearson correlation of returns.
        lead_lag: The lag (in bars) most predictive of XAUUSD.
        volatility_transmission: Lead-lag correlation of realized volatility.
        cointegration: Engle-Granger test on price levels, if enough history.
        same_regime_correlation: Rolling correlation restricted to
            historical periods sharing XAUUSD's current regime.
        feature_importance_score: A composite, always-recomputed ranking
            score (never a fixed weight) — higher means more currently
            predictive.
        recent_return_pct: This instrument's own most recent measured
            log return, as a percent — combined with `rolling_correlation`'s
            sign by callers (e.g. `src.workflows.market_update.pipeline`)
            to translate "XAUUSD correlates with X" into an implied
            XAUUSD direction, since a correlation coefficient alone has no
            direction of its own.
    """

    instrument_name: str
    category: str
    rolling_correlation: RollingCorrelationResult
    lead_lag: LeadLagResult
    volatility_transmission: LeadLagResult
    cointegration: CointegrationResult | None
    same_regime_correlation: RollingCorrelationResult
    feature_importance_score: float
    recent_return_pct: float


@dataclass(frozen=True, slots=True)
class CorrelationAnalysisResult:
    """Outcome of one full Market Correlation Engine analysis cycle.

    Attributes:
        xauusd_regime: XAUUSD's current classified regime, if enough
            history was available.
        dxy_proxy: Rolling correlation between XAUUSD and the computed
            DXY proxy, if every required FX component was available.
        instruments: Every analyzed instrument's report, ordered by
            `feature_importance_score` descending (most predictive first).
    """

    xauusd_regime: str | None
    dxy_proxy: RollingCorrelationResult | None
    instruments: list[InstrumentCorrelationReport] = field(default_factory=list)


def _feature_importance_score(
    rolling: RollingCorrelationResult, cointegration: CointegrationResult | None
) -> float:
    confidence = min(1.0, rolling.sample_size / _SAMPLE_CONFIDENCE_NORMALIZER)
    score = abs(rolling.correlation) * confidence
    if cointegration is not None and cointegration.is_cointegrated:
        score += _COINTEGRATION_BONUS
    return score


def _same_regime_correlation(
    xauusd_candles: list[Candle], returns_a: list[float], returns_b: list[float]
) -> RollingCorrelationResult:
    """Restrict `rolling_correlation` to points sharing XAUUSD's current regime."""
    if len(xauusd_candles) < _REGIME_WINDOW_SIZE + 1:
        return RollingCorrelationResult(correlation=0.0, sample_size=0)

    current_regime = classify_regime(xauusd_candles[-_REGIME_WINDOW_SIZE:]).regime
    n = min(len(returns_a), len(returns_b), len(xauusd_candles) - 1)
    same_regime_a: list[float] = []
    same_regime_b: list[float] = []
    for offset in range(n):
        # returns[i] is the return ending at candle index i+1; classify the
        # regime of the window ending at that same candle.
        candle_index = len(xauusd_candles) - n + offset
        if candle_index < _REGIME_WINDOW_SIZE:
            continue
        window = xauusd_candles[candle_index - _REGIME_WINDOW_SIZE : candle_index]
        if classify_regime(window).regime != current_regime:
            continue
        same_regime_a.append(returns_a[-n + offset])
        same_regime_b.append(returns_b[-n + offset])

    return rolling_correlation(same_regime_a, same_regime_b)


class CorrelationAnalysisService:
    """Runs the Market Correlation Engine for XAUUSD against every enabled instrument."""

    def __init__(
        self,
        *,
        candle_repository: CandleRepository,
        correlated_price_repository: CorrelatedPriceRepository,
        instrument_repository: CorrelatedInstrumentRepository,
    ) -> None:
        """Initialize the service (constructor injection).

        Args:
            candle_repository: Source of XAUUSD's own OHLCV history.
            correlated_price_repository: Source of each instrument's OHLCV history.
            instrument_repository: Source of enabled `CorrelatedInstrument` rows.
        """
        self._candles = candle_repository
        self._prices = correlated_price_repository
        self._instruments = instrument_repository

    async def analyze(
        self, xauusd_symbol_id: uuid.UUID, *, timeframe: str, lookback: int = 1000
    ) -> CorrelationAnalysisResult:
        """Run one full correlation analysis cycle.

        Args:
            xauusd_symbol_id: The platform's primary `Symbol` id (XAUUSD).
            timeframe: One of `src.models.candle.TIMEFRAMES`.
            lookback: Number of most-recent bars to analyze.

        Returns:
            A `CorrelationAnalysisResult`. Instruments with too little
            aligned history are still included, with zeroed-out
            correlations — never silently dropped or fabricated.
        """
        xauusd_candles = await self._candles.list_most_recent(
            xauusd_symbol_id, timeframe, count=lookback
        )
        xauusd_by_timestamp = {candle.timestamp: candle.close for candle in xauusd_candles}
        xauusd_regime = (
            classify_regime(xauusd_candles[-_REGIME_WINDOW_SIZE:]).regime
            if len(xauusd_candles) >= _REGIME_WINDOW_SIZE
            else None
        )

        enabled_instruments = await self._instruments.list_enabled_with_mt5_symbol()
        # Testing every enabled instrument's cointegration in the same
        # cycle is a multiple-hypothesis-testing problem: a fixed 5%
        # significance level per test compounds to a much higher combined
        # false-positive rate across N simultaneous tests. Bonferroni
        # correction (a standard, conservative fix) keeps the *combined*
        # false-positive rate near 5% instead.
        cointegration_significance_level = _BASE_COINTEGRATION_SIGNIFICANCE_LEVEL / max(
            1, len(enabled_instruments)
        )
        instrument_prices: dict[str, list[CorrelatedPrice]] = {}
        reports: list[InstrumentCorrelationReport] = []

        for instrument in enabled_instruments:
            prices = await self._prices.list_most_recent(instrument.id, timeframe, count=lookback)
            instrument_prices[instrument.name] = prices
            reports.append(
                self._analyze_one(
                    instrument,
                    prices,
                    xauusd_candles=xauusd_candles,
                    xauusd_by_timestamp=xauusd_by_timestamp,
                    cointegration_significance_level=cointegration_significance_level,
                )
            )

        reports.sort(key=lambda report: report.feature_importance_score, reverse=True)
        dxy_proxy = self._analyze_dxy_proxy(instrument_prices, xauusd_by_timestamp)
        return CorrelationAnalysisResult(
            xauusd_regime=xauusd_regime, dxy_proxy=dxy_proxy, instruments=reports
        )

    def _analyze_one(
        self,
        instrument: CorrelatedInstrument,
        prices: list[CorrelatedPrice],
        *,
        xauusd_candles: list[Candle],
        xauusd_by_timestamp: dict[datetime, float],
        cointegration_significance_level: float,
    ) -> InstrumentCorrelationReport:
        aligned_xauusd, aligned_other = _align_by_timestamp(xauusd_by_timestamp, prices)
        returns_a = log_returns(aligned_xauusd)
        returns_b = log_returns(aligned_other)

        rolling = rolling_correlation(returns_a, returns_b)
        lead_lag = lead_lag_correlation(returns_a, returns_b)
        vol_transmission = volatility_transmission(returns_a, returns_b)
        cointegration = cointegration_test(
            aligned_xauusd, aligned_other, significance_level=cointegration_significance_level
        )
        same_regime = _same_regime_correlation(xauusd_candles, returns_a, returns_b)
        recent_return_pct = returns_b[-1] * 100 if returns_b else 0.0

        return InstrumentCorrelationReport(
            instrument_name=instrument.name,
            category=instrument.category,
            rolling_correlation=rolling,
            lead_lag=lead_lag,
            volatility_transmission=vol_transmission,
            cointegration=cointegration,
            same_regime_correlation=same_regime,
            feature_importance_score=_feature_importance_score(rolling, cointegration),
            recent_return_pct=recent_return_pct,
        )

    def _analyze_dxy_proxy(
        self,
        instrument_prices: dict[str, list[CorrelatedPrice]],
        xauusd_by_timestamp: dict[datetime, float],
    ) -> RollingCorrelationResult | None:
        components = {}
        for name in _DXY_PROXY_WEIGHTS:
            prices = instrument_prices.get(name)
            if not prices:
                return None
            components[name] = {price.timestamp: price.close for price in prices}

        common_timestamps = set.intersection(*(set(series) for series in components.values()))
        common_timestamps &= set(xauusd_by_timestamp)
        if len(common_timestamps) < 2:
            return None
        ordered_timestamps = sorted(common_timestamps)

        dxy_proxy_series = [
            sum(
                _DXY_PROXY_WEIGHTS[name] * components[name][timestamp]
                for name in _DXY_PROXY_WEIGHTS
            )
            for timestamp in ordered_timestamps
        ]
        xauusd_series = [xauusd_by_timestamp[timestamp] for timestamp in ordered_timestamps]

        return rolling_correlation(log_returns(xauusd_series), log_returns(dxy_proxy_series))


def _align_by_timestamp(
    xauusd_by_timestamp: dict[datetime, float], other_prices: list[CorrelatedPrice]
) -> tuple[list[float], list[float]]:
    """Align two price series on their shared timestamps, oldest first."""
    common = sorted(
        timestamp
        for timestamp in (price.timestamp for price in other_prices)
        if timestamp in xauusd_by_timestamp
    )
    other_by_timestamp = {price.timestamp: price.close for price in other_prices}
    aligned_xauusd = [xauusd_by_timestamp[timestamp] for timestamp in common]
    aligned_other = [other_by_timestamp[timestamp] for timestamp in common]
    return aligned_xauusd, aligned_other
