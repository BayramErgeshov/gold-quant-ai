"""Unit tests for the "Before Market Close" position assessment."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from src.core.execution.mt5_client import OpenPosition
from src.engines.chief_ai.decision import ChiefAIDecision
from src.engines.statistics_engine.probability import ProbabilityEstimate
from src.models.trade import Trade
from src.workflows.reporting.pre_close_report import assess_position_before_close

pytestmark = pytest.mark.unit

_SYMBOL_ID = uuid.uuid4()


def _decision(state: str, confidence_pct: float = 80.0) -> ChiefAIDecision:
    return ChiefAIDecision(
        state=state,  # type: ignore[arg-type]
        probability=ProbabilityEstimate(
            bullish_probability=0.8, bearish_probability=0.1, neutral_probability=0.1
        ),
        confidence_pct=confidence_pct,
        uncertainty_factors=[],
        reasons=["test"],
    )


def _position(*, direction: str = "buy", profit: float = 0.0) -> OpenPosition:
    return OpenPosition(
        ticket="9001",
        symbol="XAUUSD",
        direction=direction,  # type: ignore[arg-type]
        volume=1.0,
        entry_price=2000.0,
        stop_loss=1990.0,
        take_profit=2020.0,
        current_price=2005.0,
        profit=profit,
        magic_number=42,
        opened_at=datetime.now(UTC),
    )


def _trade(**overrides: object) -> Trade:
    defaults: dict[str, object] = {
        "symbol_id": _SYMBOL_ID,
        "direction": "buy",
        "status": "open",
        "volume": 1.0,
        "entry_price": 2000.0,
        "stop_loss": 1990.0,
        "magic_number": 42,
    }
    defaults.update(overrides)
    return Trade(**defaults)


def test_recommends_keep_when_current_decision_agrees_with_position_direction() -> None:
    assessment = assess_position_before_close(
        trade=_trade(direction="buy"),
        position=_position(direction="buy"),
        current_decision=_decision("BUY", confidence_pct=85.0),
        market_regime="bull_trend",
        weekend_approaching=False,
    )

    assert assessment.recommendation == "keep"
    assert "current_decision_agrees:BUY@85%" in assessment.reasons


def test_recommends_close_when_current_decision_opposes_position_direction() -> None:
    assessment = assess_position_before_close(
        trade=_trade(direction="buy"),
        position=_position(direction="buy"),
        current_decision=_decision("SELL", confidence_pct=75.0),
        market_regime="bear_trend",
        weekend_approaching=False,
    )

    assert assessment.recommendation == "close"
    assert "current_decision_opposes:SELL@75%" in assessment.reasons


def test_falls_back_to_floating_pnl_when_decision_is_weak() -> None:
    losing = assess_position_before_close(
        trade=_trade(direction="buy"),
        position=_position(direction="buy", profit=-10.0),
        current_decision=_decision("WAIT", confidence_pct=40.0),
        market_regime="range",
        weekend_approaching=False,
    )
    winning = assess_position_before_close(
        trade=_trade(direction="buy"),
        position=_position(direction="buy", profit=10.0),
        current_decision=_decision("WAIT", confidence_pct=40.0),
        market_regime="range",
        weekend_approaching=False,
    )

    assert losing.recommendation == "close"
    assert winning.recommendation == "keep"
    assert "no_strong_directional_signal_this_cycle" in losing.reasons


def test_weekend_risk_is_none_when_weekend_not_approaching() -> None:
    assessment = assess_position_before_close(
        trade=_trade(),
        position=_position(),
        current_decision=_decision("BUY"),
        market_regime="high_volatility",
        weekend_approaching=False,
    )

    assert assessment.weekend_risk is None


def test_weekend_risk_flags_elevated_regimes() -> None:
    assessment = assess_position_before_close(
        trade=_trade(),
        position=_position(),
        current_decision=_decision("BUY"),
        market_regime="high_volatility",
        weekend_approaching=True,
    )

    assert assessment.weekend_risk is not None
    assert "Elevated weekend gap risk" in assessment.weekend_risk


def test_weekend_risk_notes_no_elevated_signal_for_calm_regimes() -> None:
    assessment = assess_position_before_close(
        trade=_trade(),
        position=_position(),
        current_decision=_decision("BUY"),
        market_regime="bull_trend",
        weekend_approaching=True,
    )

    assert assessment.weekend_risk is not None
    assert "No elevated weekend gap risk" in assessment.weekend_risk


def test_weekend_risk_handles_unclassified_regime() -> None:
    assessment = assess_position_before_close(
        trade=_trade(),
        position=_position(),
        current_decision=_decision("BUY"),
        market_regime=None,
        weekend_approaching=True,
    )

    assert assessment.weekend_risk is not None
    assert "unclassified" in assessment.weekend_risk
