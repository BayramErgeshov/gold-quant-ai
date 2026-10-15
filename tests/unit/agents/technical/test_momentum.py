"""Unit tests for `MomentumAgent`."""

from __future__ import annotations

import pytest

from src.agents.technical.momentum import MomentumAgent, detect_rsi_divergence
from src.models.candle import Candle
from tests.unit.agents.technical._helpers import make_candle, make_series

pytestmark = pytest.mark.unit


def _double_extremum_candles(*, sign: int) -> list[Candle]:
    """Build a "double top/bottom" series with a genuine price/RSI divergence.

    `sign=1` builds a bearish divergence (second peak is a higher price
    high reached via a much gentler climb, so Wilder's RSI reads lower
    there than at the first, sharper peak). `sign=-1` mirrors this into a
    bullish divergence (a lower price low with a higher RSI reading).
    Each extremum is deliberately isolated (a single candle's high/low
    strictly exceeds its neighbors) so `find_swing_points` detects exactly
    one fractal point per peak/trough, and enough history precedes the
    first extremum for RSI(14) to be defined there.
    """
    candles: list[Candle] = []
    index = 0

    for _ in range(10):  # warm-up so the first extremum has RSI(14) history
        candles.append(make_candle(index, open_=99.5, high=100.5, low=99.0, close=100.0))
        index += 1

    first_leg = [100.0 + sign * i * 2 for i in range(9)] + [100.0 + sign * 15.0]
    for position, close in enumerate(first_leg):
        extreme = close + sign * 4.0
        is_peak = position == len(first_leg) - 1
        high = extreme if (sign > 0 and is_peak) else close + 1.0
        low = extreme if (sign < 0 and is_peak) else close - 1.0
        candles.append(
            make_candle(index, open_=close - sign * 0.5, high=high, low=low, close=close)
        )
        index += 1

    pullback = [100.0 + sign * 10.0 - sign * i * 2 for i in range(8)]
    for close in pullback:
        candles.append(
            make_candle(
                index, open_=close + sign * 0.5, high=close + 1.0, low=close - 1.0, close=close
            )
        )
        index += 1

    second_leg_count = 21
    second_leg = [100.0 - sign * 5.0 + sign * i * 1.1 for i in range(second_leg_count - 1)] + [
        100.0 + sign * 17.0
    ]
    for position, close in enumerate(second_leg):
        extreme = close + sign * 3.0
        is_peak = position == len(second_leg) - 1
        high = extreme if (sign > 0 and is_peak) else close + 1.0
        low = extreme if (sign < 0 and is_peak) else close - 1.0
        candles.append(
            make_candle(index, open_=close - sign * 0.5, high=high, low=low, close=close)
        )
        index += 1

    tail = [100.0 + sign * 13.0 - sign * i * 1.5 for i in range(6)]
    for close in tail:
        candles.append(
            make_candle(
                index, open_=close + sign * 0.5, high=close + 1.0, low=close - 1.0, close=close
            )
        )
        index += 1

    return candles


def test_analyze_reports_unknown_with_insufficient_candles() -> None:
    agent = MomentumAgent()
    candles = make_series([100.0, 101.0, 102.0])

    report = agent.analyze(candles)

    assert report.bias == "neutral"
    assert report.confidence == 0.0
    assert report.unknowns


def test_analyze_is_bullish_for_a_strong_sustained_uptrend() -> None:
    agent = MomentumAgent()
    closes = [100.0 + i * 1.5 for i in range(60)]
    candles = make_series(closes, spread=0.3)

    report = agent.analyze(candles)

    assert report.bias == "bullish"
    assert report.confidence > 0.0
    assert "rsi" in report.metrics
    assert "macd_histogram" in report.metrics
    assert "roc_pct" in report.metrics
    assert "stochastic_k" in report.metrics


def test_analyze_is_bearish_for_a_strong_sustained_downtrend() -> None:
    agent = MomentumAgent()
    closes = [200.0 - i * 1.5 for i in range(60)]
    candles = make_series(closes, spread=0.3)

    report = agent.analyze(candles)

    assert report.bias == "bearish"
    assert report.confidence > 0.0


def test_analyze_is_neutral_for_a_flat_choppy_market() -> None:
    agent = MomentumAgent()
    # Mild noise, settling into a long flat stretch -- every indicator's
    # recent-history-weighted reading converges toward neutral.
    noise = [100.0, 100.5, 99.7, 100.3, 99.8, 100.2, 99.9] * 3
    flat_tail = [100.0] * 30
    candles = make_series(noise + flat_tail, spread=0.1)

    report = agent.analyze(candles)

    assert report.bias == "neutral"


def test_analyze_flags_overbought_rsi() -> None:
    agent = MomentumAgent()
    closes = [100.0 + i for i in range(40)]  # strictly increasing -> RSI 100
    candles = make_series(closes, spread=0.2)

    report = agent.analyze(candles)

    assert any("overbought" in reason for reason in report.opposing_evidence)


def test_analyze_flags_oversold_rsi() -> None:
    agent = MomentumAgent()
    closes = [200.0 - i for i in range(40)]  # strictly decreasing -> RSI 0
    candles = make_series(closes, spread=0.2)

    report = agent.analyze(candles)

    assert any("oversold" in reason for reason in report.opposing_evidence)


def test_detect_rsi_divergence_returns_none_with_insufficient_candles() -> None:
    candles = make_series([100.0, 101.0, 102.0])

    assert detect_rsi_divergence(candles) is None


def test_detect_rsi_divergence_finds_bearish_divergence() -> None:
    # Second peak is a higher price high reached via a much gentler climb
    # -- Wilder's RSI reads lower there than at the first, sharper peak.
    candles = _double_extremum_candles(sign=1)

    divergence = detect_rsi_divergence(candles)

    assert divergence == "bearish"


def test_detect_rsi_divergence_finds_bullish_divergence() -> None:
    # Mirror of the bearish case: a lower price low reached gently, with
    # a higher RSI reading than the first, sharper low.
    candles = _double_extremum_candles(sign=-1)

    divergence = detect_rsi_divergence(candles)

    assert divergence == "bullish"


def test_detect_rsi_divergence_returns_none_when_trend_is_consistent() -> None:
    closes = [100.0 + i for i in range(60)]  # strictly increasing, no divergence
    candles = make_series(closes, spread=0.2)

    assert detect_rsi_divergence(candles) is None


def test_analyze_surfaces_detected_divergence_as_opposing_evidence() -> None:
    agent = MomentumAgent()
    candles = _double_extremum_candles(sign=1)

    report = agent.analyze(candles)

    assert any("divergence" in reason for reason in report.opposing_evidence)
