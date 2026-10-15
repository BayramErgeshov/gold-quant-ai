"""Unit tests for trade outcome factor analysis."""

from __future__ import annotations

import uuid

import pytest

from src.engines.learning_engine.factor_analysis import (
    TradeContext,
    analyze_department_disagreement,
    analyze_losing_trade,
    analyze_winning_trade,
    department_correctness,
    department_direction,
    disagreeing_departments,
    missing_departments,
    outcome_direction,
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
    return Trade(**defaults)


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


def test_disagreeing_departments_finds_opposing_bias() -> None:
    trade = _trade(
        direction="buy",
        department_votes={
            "technical": {"bias": "bullish", "confidence": 0.8},
            "macro": {"bias": "bearish", "confidence": 0.6},
        },
    )

    assert disagreeing_departments(trade) == ["macro"]


def test_disagreeing_departments_empty_when_none_recorded() -> None:
    assert disagreeing_departments(_trade(department_votes=None)) == []


def test_disagreeing_departments_empty_when_all_agree() -> None:
    trade = _trade(
        direction="sell",
        department_votes={"technical": {"bias": "bearish", "confidence": 0.8}},
    )

    assert disagreeing_departments(trade) == []


def test_missing_departments_reports_absent_opinion_departments() -> None:
    trade = _trade(department_votes={"technical": {"bias": "bullish", "confidence": 0.8}})

    missing = missing_departments(trade)

    assert "macro" in missing
    assert "technical" not in missing


def test_missing_departments_reports_all_when_none_recorded() -> None:
    missing = missing_departments(_trade(department_votes=None))

    assert "technical" in missing
    assert "macro" in missing


def test_analyze_department_disagreement_builds_one_factor_per_department() -> None:
    trade = _trade(
        direction="buy",
        department_votes={
            "macro": {"bias": "bearish", "confidence": 0.65},
            "news": {"bias": "bearish", "confidence": 0.55},
            "technical": {"bias": "bullish", "confidence": 0.8},
        },
    )

    factors = analyze_department_disagreement(trade)

    assert len(factors) == 2
    assert {factor.name for factor in factors} == {
        "department_disagreed:macro",
        "department_disagreed:news",
    }
    assert any("65%" in factor.detail for factor in factors)


def test_known_regime_is_flagged_for_win() -> None:
    factors = analyze_winning_trade(_trade(), _context())

    assert any(factor.name == "known_market_regime" for factor in factors)


def test_outcome_direction_reflects_win_or_loss_relative_to_entry_direction() -> None:
    assert outcome_direction(_trade(direction="buy", realized_pnl=10.0)) == 1
    assert outcome_direction(_trade(direction="buy", realized_pnl=-10.0)) == -1
    assert outcome_direction(_trade(direction="sell", realized_pnl=10.0)) == -1
    assert outcome_direction(_trade(direction="sell", realized_pnl=-10.0)) == 1
    assert outcome_direction(_trade(realized_pnl=None)) is None


def test_department_direction_maps_bias_to_sign() -> None:
    assert department_direction("bullish") == 1
    assert department_direction("bearish") == -1
    assert department_direction("neutral") is None
    assert department_direction(None) is None


def test_department_correctness_compares_against_the_realized_outcome_not_entry_direction() -> None:
    # A winning buy: a bullish vote was right, a bearish vote was wrong --
    # distinct from `disagreeing_departments`, which would only flag the
    # bearish one relative to the ENTRY direction (same result here by
    # coincidence, but the two functions measure different things).
    trade = _trade(
        direction="buy",
        realized_pnl=10.0,
        department_votes={
            "technical": {"bias": "bullish", "confidence": 0.8},
            "macro": {"bias": "bearish", "confidence": 0.6},
            "news": {"bias": "neutral", "confidence": 0.5},
        },
    )

    correctness = department_correctness(trade)

    assert correctness == {"technical": True, "macro": False}


def test_department_correctness_flags_agreeing_departments_wrong_on_a_losing_trade() -> None:
    # A losing buy: the bullish vote that agreed with the entry is now
    # judged WRONG against the actual outcome -- the whole point of
    # comparing to realized price movement, not the entry decision.
    trade = _trade(
        direction="buy",
        realized_pnl=-10.0,
        department_votes={"technical": {"bias": "bullish", "confidence": 0.8}},
    )

    assert department_correctness(trade) == {"technical": False}


def test_department_correctness_is_empty_without_a_known_outcome() -> None:
    trade = _trade(
        realized_pnl=None,
        department_votes={"technical": {"bias": "bullish", "confidence": 0.8}},
    )

    assert department_correctness(trade) == {}


def test_department_correctness_is_empty_without_department_votes() -> None:
    assert department_correctness(_trade(realized_pnl=10.0, department_votes=None)) == {}
