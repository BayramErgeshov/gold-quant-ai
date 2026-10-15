"""Unit tests for `LiveTradingLoop`'s pure-function helpers."""

from __future__ import annotations

import pytest

from src.core.agents.confluence import CombinedVote
from src.core.agents.report import AgentReport
from src.engines.chief_ai.decision import ChiefAIDecision
from src.engines.risk_engine.exposure import ExposureLimits
from src.engines.statistics_engine.probability import ProbabilityEstimate
from src.models.runtime_settings import RuntimeSettings
from src.services.scheduler.live_loop import (
    _apply_runtime_settings,
    _build_dynamic_stop_inputs,
    _demo_learning_discount,
)
from src.workflows.market_update.pipeline import MarketScanConfig, MarketScanResult

pytestmark = pytest.mark.unit


def _scan_config() -> MarketScanConfig:
    import uuid

    return MarketScanConfig(
        symbol_id=uuid.uuid4(),
        mt5_symbol="XAUUSD",
        timeframe="M15",
        window_size=20,
        risk_per_trade_pct=0.5,
        atr_multiplier_for_stop=1.5,
        max_spread_points=350.0,
        confidence_threshold=70.0,
        exposure_limits=ExposureLimits(
            max_total_exposure_pct=5.0,
            max_instrument_exposure_pct=5.0,
            max_correlated_exposure_pct=7.5,
            max_session_exposure_pct=10.0,
            max_daily_exposure_pct=10.0,
        ),
        account_type="demo",
        expected_account=None,
        live_trading_approved=False,
        strategy_name="xauusd_m15_live",
        strategy_version="1.0.0",
        telegram_chat_id="chat-1",
    )


def _runtime_settings(**overrides: object) -> RuntimeSettings:
    defaults: dict[str, object] = {
        "id": "default",
        "fixed_lot_size": None,
        "auto_trading_enabled": True,
        "confidence_threshold": None,
        "scalping_enabled": True,
        "risk_mode": "normal",
    }
    defaults.update(overrides)
    return RuntimeSettings(**defaults)


def test_apply_runtime_settings_defaults_leave_config_unchanged() -> None:
    config = _scan_config()

    effective = _apply_runtime_settings(config, _runtime_settings())

    assert effective.risk_per_trade_pct == pytest.approx(config.risk_per_trade_pct)
    assert effective.fixed_lot_size is None
    assert effective.confidence_threshold == pytest.approx(config.confidence_threshold)


def test_apply_runtime_settings_overrides_fixed_lot_size() -> None:
    effective = _apply_runtime_settings(_scan_config(), _runtime_settings(fixed_lot_size=0.25))

    assert effective.fixed_lot_size == pytest.approx(0.25)


def test_apply_runtime_settings_overrides_confidence_threshold() -> None:
    effective = _apply_runtime_settings(
        _scan_config(), _runtime_settings(confidence_threshold=85.0)
    )

    assert effective.confidence_threshold == pytest.approx(85.0)


def test_apply_runtime_settings_conservative_risk_mode_halves_risk() -> None:
    config = _scan_config()

    effective = _apply_runtime_settings(config, _runtime_settings(risk_mode="conservative"))

    assert effective.risk_per_trade_pct == pytest.approx(config.risk_per_trade_pct * 0.5)


def test_apply_runtime_settings_aggressive_risk_mode_increases_risk() -> None:
    config = _scan_config()

    effective = _apply_runtime_settings(config, _runtime_settings(risk_mode="aggressive"))

    assert effective.risk_per_trade_pct == pytest.approx(config.risk_per_trade_pct * 1.5)


def test_apply_runtime_settings_demo_learning_mode_discounts_confidence_threshold() -> None:
    effective = _apply_runtime_settings(
        _scan_config(),
        _runtime_settings(confidence_threshold=85.0, demo_learning_mode_enabled=True),
    )

    assert effective.confidence_threshold == pytest.approx(75.0)


def test_apply_runtime_settings_demo_learning_mode_floors_the_discount() -> None:
    effective = _apply_runtime_settings(
        _scan_config(),
        _runtime_settings(confidence_threshold=55.0, demo_learning_mode_enabled=True),
    )

    assert effective.confidence_threshold == pytest.approx(50.0)


def test_apply_runtime_settings_demo_learning_mode_off_leaves_threshold_unchanged() -> None:
    effective = _apply_runtime_settings(
        _scan_config(),
        _runtime_settings(confidence_threshold=85.0, demo_learning_mode_enabled=False),
    )

    assert effective.confidence_threshold == pytest.approx(85.0)


def test_apply_runtime_settings_demo_learning_mode_does_not_discount_the_engines_own_default() -> (
    None
):
    # Per this helper's own scoping: only a threshold the user actually
    # set gets discounted -- an engine's private hardcoded default
    # (`confidence_threshold` left None) is left completely alone.
    config = _scan_config()

    effective = _apply_runtime_settings(
        config, _runtime_settings(confidence_threshold=None, demo_learning_mode_enabled=True)
    )

    assert effective.confidence_threshold == pytest.approx(config.confidence_threshold)


def test_apply_runtime_settings_demo_learning_mode_discounts_min_trade_quality_score() -> None:
    effective = _apply_runtime_settings(
        _scan_config(),
        _runtime_settings(min_trade_quality_score=70.0, demo_learning_mode_enabled=True),
    )

    assert effective.min_trade_quality_score == pytest.approx(60.0)


def test_apply_runtime_settings_forwards_demo_learning_mode_to_the_effective_config() -> None:
    # Per the investigation into why Intraday rarely trades: the Risk
    # Engine's own executable confidence-tier floor
    # (`src.engines.risk_engine.approval`) is independent of and normally
    # stricter than `confidence_threshold` -- Demo Learning Mode must
    # reach `MarketScanConfig.demo_learning_mode` so `TradeApprovalRequest`
    # actually widens that floor, not just the Chief AI threshold.
    effective = _apply_runtime_settings(
        _scan_config(), _runtime_settings(demo_learning_mode_enabled=True)
    )

    assert effective.demo_learning_mode is True


def test_apply_runtime_settings_demo_learning_mode_off_by_default() -> None:
    effective = _apply_runtime_settings(_scan_config(), _runtime_settings())

    assert effective.demo_learning_mode is False


def test_demo_learning_discount_returns_none_for_none_input() -> None:
    assert _demo_learning_discount(None, _runtime_settings(demo_learning_mode_enabled=True)) is None


def test_demo_learning_discount_is_a_no_op_when_mode_disabled() -> None:
    result = _demo_learning_discount(85.0, _runtime_settings(demo_learning_mode_enabled=False))

    assert result == pytest.approx(85.0)


def test_demo_learning_discount_never_drops_below_the_floor() -> None:
    result = _demo_learning_discount(51.0, _runtime_settings(demo_learning_mode_enabled=True))

    assert result == pytest.approx(50.0)


def _decision() -> ChiefAIDecision:
    return ChiefAIDecision(
        state="WAIT",
        probability=ProbabilityEstimate(
            bullish_probability=0.4, bearish_probability=0.4, neutral_probability=0.2
        ),
        confidence_pct=50.0,
        uncertainty_factors=[],
        reasons=["test"],
    )


def _technical_vote(
    *, atr_ratio: float | None, trend_bias: str, support: float, resistance: float
) -> CombinedVote:
    reports = [
        AgentReport(
            agent_name="volatility",
            bias="neutral",
            confidence=0.6,
            metrics={} if atr_ratio is None else {"atr_ratio": atr_ratio},
        ),
        AgentReport(agent_name="trend", bias=trend_bias, confidence=0.7),  # type: ignore[arg-type]
        AgentReport(
            agent_name="support_resistance",
            bias="neutral",
            confidence=0.5,
            metrics={"nearest_support": support, "nearest_resistance": resistance},
        ),
    ]
    return CombinedVote(
        bullish_probability=0.5,
        bearish_probability=0.3,
        neutral_probability=0.2,
        confidence=0.6,
        quality_grade="A",
        strongest_supporting_factors=[],
        strongest_opposing_factors=[],
        agent_reports=reports,
    )


def _order_flow_vote(*, bullish: float, bearish: float, confidence: float) -> CombinedVote:
    return CombinedVote(
        bullish_probability=bullish,
        bearish_probability=bearish,
        neutral_probability=1.0 - bullish - bearish,
        confidence=confidence,
        quality_grade="B",
        strongest_supporting_factors=[],
        strongest_opposing_factors=[],
    )


def test_extracts_atr_ratio_trend_and_support_resistance_from_technical_reports() -> None:
    scan_result = MarketScanResult(
        decision=_decision(),
        market_regime="bull_trend",
        department_votes={
            "technical": _technical_vote(
                atr_ratio=1.4, trend_bias="bullish", support=1995.0, resistance=2010.0
            )
        },
    )

    inputs = _build_dynamic_stop_inputs(scan_result)

    assert inputs.atr_ratio == pytest.approx(1.4)
    assert inputs.htf_trend_bias == "bullish"
    assert inputs.nearest_support == pytest.approx(1995.0)
    assert inputs.nearest_resistance == pytest.approx(2010.0)
    assert inputs.market_regime == "bull_trend"
    assert inputs.news_risk_imminent is False


def test_extracts_order_flow_bias_and_confidence_when_present() -> None:
    scan_result = MarketScanResult(
        decision=_decision(),
        department_votes={
            "technical": _technical_vote(
                atr_ratio=1.0, trend_bias="neutral", support=1990.0, resistance=2020.0
            ),
            "order_flow": _order_flow_vote(bullish=0.2, bearish=0.7, confidence=0.8),
        },
    )

    inputs = _build_dynamic_stop_inputs(scan_result)

    assert inputs.order_flow_bias == "bearish"
    assert inputs.order_flow_confidence == pytest.approx(0.8)


def test_defaults_are_honest_when_no_departments_present() -> None:
    scan_result = MarketScanResult(decision=_decision())

    inputs = _build_dynamic_stop_inputs(scan_result)

    assert inputs.atr_ratio is None
    assert inputs.htf_trend_bias is None
    assert inputs.nearest_support is None
    assert inputs.nearest_resistance is None
    assert inputs.order_flow_bias is None
    assert inputs.order_flow_confidence == pytest.approx(0.0)
    assert inputs.market_regime is None
