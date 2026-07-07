"""Unit tests for trade outcome factor analysis."""

from __future__ import annotations

import uuid

import pytest

from src.engines.learning_engine.factor_analysis import (
    TradeContext,
    analyze_losing_trade,
    analyze_winning_trade,
)
from src.models.trade import Trade

pytestmark = pytest.mark.unit

_SYMBOL_ID = uuid.uuid4()


def _trade(**overrides: object) -> Trade:
    defaults: dict[str, object] = {
        "symbol_id": _SYMBOL_ID,
        "direction": "buy",
        "status": "closed",
        "volume": 1.0,
        "entry_price": 2000.0,
        "stop_loss": 1990.0,
        "magic_number": 42,
    }
    defaults.update(overrides)
    return Trade(**defaults)  # type: ignore[arg-type]


def _context(**overrides: object) -> TradeContext:
    defaults: dict[str, object] = {
        "confidence_pct": 80.0,
        "confidence_threshold": 70.0,
        "historical_edge_pct": 0.5,
        "min_historical_edge_pct": 0.2,
        "market_regime": "bull_trend",
        "news_imminent_at_entry": False,
        "expected_volatility_pct": 1.0,
    }
    defaults.update(overrides)
    return TradeContext(**defaults)  # type: ignore[arg-type]


def test_no_factors_for_clean_losing_trade() -> None:
    factors = analyze_losing_trade(_trade(), _context())

    assert factors == []


def test_low_confidence_is_flagged() -> None:
    factors = analyze_losing_trade(_trade(), _context(confidence_pct=50.0))

    assert any(factor.name == "confidence_below_threshold" for factor in factors)


def test_weak_historical_edge_is_flagged() -> None:
    factors = analyze_losing_trade(
        _trade(), _context(historical_edge_pct=0.1, min_historical_edge_pct=0.3)
    )

    assert any(factor.name == "weak_historical_edge" for factor in factors)


def test_unknown_regime_is_flagged() -> None:
    factors = analyze_losing_trade(_trade(), _context(market_regime=None))

    assert any(factor.name == "unknown_market_regime" for factor in factors)


def test_news_imminent_is_flagged() -> None:
    factors = analyze_losing_trade(_trade(), _context(news_imminent_at_entry=True))

    assert any(factor.name == "news_ignored" for factor in factors)


def test_stop_too_close_is_flagged() -> None:
    trade = _trade(entry_price=2000.0, stop_loss=1999.0)  # 0.05% distance
    factors = analyze_losing_trade(trade, _context(expected_volatility_pct=1.0))

    assert any(factor.name == "stop_too_close" for factor in factors)


def test_stop_not_flagged_without_expected_volatility() -> None:
    trade = _trade(entry_price=2000.0, stop_loss=1999.0)
    factors = analyze_losing_trade(trade, _context(expected_volatility_pct=None))

    assert not any(factor.name == "stop_too_close" for factor in factors)


def test_stop_not_flagged_without_entry_price() -> None:
    trade = _trade(entry_price=None)
    factors = analyze_losing_trade(trade, _context())

    assert not any(factor.name == "stop_too_close" for factor in factors)


def test_multiple_mistake_factors_reported_together() -> None:
    factors = analyze_losing_trade(
        _trade(), _context(confidence_pct=10.0, news_imminent_at_entry=True)
    )

    names = {factor.name for factor in factors}
    assert "confidence_below_threshold" in names
    assert "news_ignored" in names


def test_no_factors_for_neutral_winning_context() -> None:
    factors = analyze_winning_trade(
        _trade(),
        _context(
            confidence_pct=50.0,
            confidence_threshold=70.0,
            historical_edge_pct=0.1,
            min_historical_edge_pct=0.3,
            market_regime=None,
        ),
    )

    assert factors == []


def test_confidence_above_threshold_is_flagged_for_win() -> None:
    factors = analyze_winning_trade(_trade(), _context())

    assert any(factor.name == "confidence_above_threshold" for factor in factors)


def test_strong_historical_edge_is_flagged_for_win() -> None:
    factors = analyze_winning_trade(_trade(), _context())

    assert any(factor.name == "strong_historical_edge" for factor in factors)


def test_known_regime_is_flagged_for_win() -> None:
    factors = analyze_winning_trade(_trade(), _context())

    assert any(factor.name == "known_market_regime" for factor in factors)
