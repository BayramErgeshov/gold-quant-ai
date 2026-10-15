"""Integration tests for `CorrelationAnalysisService`."""

from __future__ import annotations

import math
import random
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from src.engines.correlation_engine.analysis import CorrelationAnalysisService
from src.models.candle import Candle
from src.models.correlated_instrument import CorrelatedInstrument
from src.models.correlated_price import CorrelatedPrice
from src.models.symbol import Symbol
from src.repositories.candle_repository import CandleRepository
from src.repositories.correlated_instrument_repository import CorrelatedInstrumentRepository
from src.repositories.correlated_price_repository import CorrelatedPriceRepository
from src.repositories.symbol_repository import SymbolRepository

_BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


def _series(count: int, *, seed: int) -> list[float]:
    rng = random.Random(seed)
    prices = [3000.0]
    for _ in range(count - 1):
        prices.append(prices[-1] + rng.gauss(0, 5))
    return prices


async def _seed_xauusd(session: AsyncSession, closes: list[float]) -> Symbol:
    symbol = await SymbolRepository(session).add(Symbol(name="XAUUSD", display_name="Gold"))
    candles = [
        Candle(
            symbol_id=symbol.id,
            timeframe="H1",
            timestamp=_BASE_TIME + timedelta(hours=index),
            open=close,
            high=close + 1,
            low=close - 1,
            close=close,
            source="test_fixture",
        )
        for index, close in enumerate(closes)
    ]
    await CandleRepository(session).insert_new(candles)
    return symbol


async def _seed_instrument(
    session: AsyncSession, *, name: str, closes: list[float], enabled: bool = True
) -> CorrelatedInstrument:
    instrument = await CorrelatedInstrumentRepository(session).add(
        CorrelatedInstrument(
            name=name,
            display_name=name,
            mt5_symbol=name,
            category="fx",
            is_enabled=enabled,
        )
    )
    prices = [
        CorrelatedPrice(
            instrument_id=instrument.id,
            timeframe="H1",
            timestamp=_BASE_TIME + timedelta(hours=index),
            open=close,
            high=close + 1,
            low=close - 1,
            close=close,
            source="test_fixture",
        )
        for index, close in enumerate(closes)
    ]
    await CorrelatedPriceRepository(session).insert_new(prices)
    return instrument


def _service(session: AsyncSession) -> CorrelationAnalysisService:
    return CorrelationAnalysisService(
        candle_repository=CandleRepository(session),
        correlated_price_repository=CorrelatedPriceRepository(session),
        instrument_repository=CorrelatedInstrumentRepository(session),
    )


async def test_analyze_ranks_a_closely_tracking_instrument_highest(
    session: AsyncSession,
) -> None:
    xauusd_closes = _series(300, seed=1)
    symbol = await _seed_xauusd(session, xauusd_closes)
    # Tracks XAUUSD almost exactly (scaled) -> should rank first.
    await _seed_instrument(
        session, name="TRACKER", closes=[close * 0.02 for close in xauusd_closes]
    )
    # Unrelated random walk -> should rank lower.
    await _seed_instrument(session, name="UNRELATED", closes=_series(300, seed=99))

    result = await _service(session).analyze(symbol.id, timeframe="H1", lookback=500)

    assert len(result.instruments) == 2
    assert result.instruments[0].instrument_name == "TRACKER"
    assert abs(result.instruments[0].rolling_correlation.correlation) > abs(
        result.instruments[1].rolling_correlation.correlation
    )
    assert result.xauusd_regime is not None


async def test_analyze_excludes_disabled_instruments(session: AsyncSession) -> None:
    xauusd_closes = _series(300, seed=1)
    symbol = await _seed_xauusd(session, xauusd_closes)
    await _seed_instrument(session, name="DISABLED", closes=xauusd_closes, enabled=False)

    result = await _service(session).analyze(symbol.id, timeframe="H1", lookback=500)

    assert result.instruments == []


async def test_analyze_computes_dxy_proxy_when_all_components_present(
    session: AsyncSession,
) -> None:
    xauusd_closes = _series(300, seed=1)
    symbol = await _seed_xauusd(session, xauusd_closes)
    for name in ("EURUSD", "USDJPY", "GBPUSD", "USDCAD", "USDCHF"):
        await _seed_instrument(session, name=name, closes=_series(300, seed=hash(name) % 1000))

    result = await _service(session).analyze(symbol.id, timeframe="H1", lookback=500)

    assert result.dxy_proxy is not None


async def test_analyze_dxy_proxy_is_none_when_a_component_is_missing(
    session: AsyncSession,
) -> None:
    xauusd_closes = _series(300, seed=1)
    symbol = await _seed_xauusd(session, xauusd_closes)
    for name in ("EURUSD", "USDJPY", "GBPUSD"):
        await _seed_instrument(session, name=name, closes=_series(300, seed=hash(name) % 1000))

    result = await _service(session).analyze(symbol.id, timeframe="H1", lookback=500)

    assert result.dxy_proxy is None


async def test_analyze_handles_instrument_with_no_overlapping_history(
    session: AsyncSession,
) -> None:
    xauusd_closes = _series(300, seed=1)
    symbol = await _seed_xauusd(session, xauusd_closes)
    # Entirely disjoint timestamps: no aligned observations at all.
    instrument = await CorrelatedInstrumentRepository(session).add(
        CorrelatedInstrument(
            name="NO_OVERLAP", display_name="No Overlap", mt5_symbol="NO_OVERLAP", category="fx"
        )
    )
    disjoint_prices = [
        CorrelatedPrice(
            instrument_id=instrument.id,
            timeframe="H1",
            timestamp=_BASE_TIME - timedelta(hours=index + 1000),
            open=1.0,
            high=1.1,
            low=0.9,
            close=1.0,
            source="test_fixture",
        )
        for index in range(10)
    ]
    await CorrelatedPriceRepository(session).insert_new(disjoint_prices)

    result = await _service(session).analyze(symbol.id, timeframe="H1", lookback=500)

    assert len(result.instruments) == 1
    assert result.instruments[0].rolling_correlation.sample_size == 0
    assert result.instruments[0].feature_importance_score == 0.0
    assert not math.isnan(result.instruments[0].rolling_correlation.correlation)


async def test_analyze_same_regime_correlation_is_zero_with_too_little_xauusd_history(
    session: AsyncSession,
) -> None:
    xauusd_closes = _series(15, seed=1)  # fewer than the regime window size
    symbol = await _seed_xauusd(session, xauusd_closes)
    await _seed_instrument(session, name="TRACKER", closes=xauusd_closes)

    result = await _service(session).analyze(symbol.id, timeframe="H1", lookback=500)

    assert result.xauusd_regime is None
    assert result.instruments[0].same_regime_correlation.sample_size == 0
    assert result.instruments[0].same_regime_correlation.correlation == 0.0


async def test_analyze_dxy_proxy_is_none_without_overlapping_timestamps(
    session: AsyncSession,
) -> None:
    xauusd_closes = _series(300, seed=1)
    symbol = await _seed_xauusd(session, xauusd_closes)
    for name in ("EURUSD", "USDJPY", "GBPUSD", "USDCAD", "USDCHF"):
        instrument = await CorrelatedInstrumentRepository(session).add(
            CorrelatedInstrument(name=name, display_name=name, mt5_symbol=name, category="fx")
        )
        disjoint_prices = [
            CorrelatedPrice(
                instrument_id=instrument.id,
                timeframe="H1",
                timestamp=_BASE_TIME - timedelta(hours=index + 5000),
                open=1.0,
                high=1.1,
                low=0.9,
                close=1.0,
                source="test_fixture",
            )
            for index in range(10)
        ]
        await CorrelatedPriceRepository(session).insert_new(disjoint_prices)

    result = await _service(session).analyze(symbol.id, timeframe="H1", lookback=500)

    assert result.dxy_proxy is None
