"""Unit tests for the Chief AI decision pipeline."""

from __future__ import annotations

import pytest

from src.core.agents.confluence import CombinedVote
from src.engines.chief_ai.decision import REQUIRED_REPORTS, ChiefAIInput, evaluate
from src.engines.risk_engine.approval import TradeApprovalDecision

pytestmark = pytest.mark.unit


def _vote(bullish: float, bearish: float, neutral: float, confidence: float) -> CombinedVote:
    return CombinedVote(
        bullish_probability=bullish,
        bearish_probability=bearish,
        neutral_probability=neutral,
        confidence=confidence,
        quality_grade="A",
        strongest_supporting_factors=["supporting_factor"],
        strongest_opposing_factors=["opposing_factor"],
    )


def _all_reports_present() -> dict[str, bool]:
    return dict.fromkeys(REQUIRED_REPORTS, True)


def _approved_risk() -> TradeApprovalDecision:
    return TradeApprovalDecision(
        approved=True, confidence_level="high_quality", rejection_reasons=[]
    )


def _rejected_risk() -> TradeApprovalDecision:
    return TradeApprovalDecision(
        approved=False,
        confidence_level="reject",
        rejection_reasons=["spread_excessive"],
    )


def test_waits_when_a_required_report_is_missing() -> None:
    reports = _all_reports_present()
    reports["ml"] = False

    decision = evaluate(
        ChiefAIInput(
            department_votes={"technical": _vote(0.8, 0.1, 0.1, confidence=0.9)},
            reports_present=reports,
            risk_decision=_approved_risk(),
            market_regime="bull_trend",
        )
    )

    assert decision.state == "WAIT"
    assert "required_report_missing" in decision.reasons
    assert any(factor.startswith("missing_report:ml") for factor in decision.uncertainty_factors)


def test_waits_when_risk_rejects() -> None:
    decision = evaluate(
        ChiefAIInput(
            department_votes={
                "technical": _vote(0.8, 0.1, 0.1, confidence=0.9),
                "macro": _vote(0.7, 0.2, 0.1, confidence=0.8),
            },
            reports_present=_all_reports_present(),
            risk_decision=_rejected_risk(),
            market_regime="bull_trend",
        )
    )

    assert decision.state == "WAIT"
    assert any(reason.startswith("risk_rejected:") for reason in decision.reasons)


def test_waits_when_confidence_below_threshold() -> None:
    decision = evaluate(
        ChiefAIInput(
            department_votes={
                "technical": _vote(0.8, 0.1, 0.1, confidence=0.3),
                "macro": _vote(0.7, 0.2, 0.1, confidence=0.2),
            },
            reports_present=_all_reports_present(),
            risk_decision=_approved_risk(),
            confidence_threshold=70.0,
            market_regime="bull_trend",
        )
    )

    assert decision.state == "WAIT"
    assert any("confidence_below_threshold" in reason for reason in decision.reasons)


def test_waits_on_conflicting_departments() -> None:
    decision = evaluate(
        ChiefAIInput(
            department_votes={
                "technical": _vote(0.5, 0.45, 0.05, confidence=0.9),
                "macro": _vote(0.45, 0.5, 0.05, confidence=0.9),
            },
            reports_present=_all_reports_present(),
            risk_decision=_approved_risk(),
            confidence_threshold=10.0,
            market_regime="range",
        )
    )

    assert decision.state == "WAIT"
    assert "conflicting_departments" in decision.uncertainty_factors


def test_waits_on_unknown_market_regime() -> None:
    decision = evaluate(
        ChiefAIInput(
            department_votes={"technical": _vote(0.9, 0.05, 0.05, confidence=0.9)},
            reports_present=_all_reports_present(),
            risk_decision=_approved_risk(),
            confidence_threshold=10.0,
            market_regime=None,
        )
    )

    assert decision.state == "WAIT"
    assert "unknown_market_regime" in decision.uncertainty_factors


def test_buys_when_bullish_probability_dominates() -> None:
    decision = evaluate(
        ChiefAIInput(
            department_votes={
                "technical": _vote(0.9, 0.05, 0.05, confidence=0.9),
                "macro": _vote(0.85, 0.1, 0.05, confidence=0.8),
            },
            reports_present=_all_reports_present(),
            risk_decision=_approved_risk(),
            confidence_threshold=50.0,
            market_regime="bull_trend",
        )
    )

    assert decision.state == "BUY"
    assert decision.probability.bullish_probability > decision.probability.bearish_probability
    assert "supporting_factor" in decision.supporting_evidence
    assert "opposing_factor" in decision.opposing_evidence


def test_sells_when_bearish_probability_dominates() -> None:
    decision = evaluate(
        ChiefAIInput(
            department_votes={
                "technical": _vote(0.05, 0.9, 0.05, confidence=0.9),
                "macro": _vote(0.1, 0.85, 0.05, confidence=0.8),
            },
            reports_present=_all_reports_present(),
            risk_decision=_approved_risk(),
            confidence_threshold=50.0,
            market_regime="bear_trend",
        )
    )

    assert decision.state == "SELL"


def test_critical_news_imminent_forces_wait() -> None:
    decision = evaluate(
        ChiefAIInput(
            department_votes={"technical": _vote(0.9, 0.05, 0.05, confidence=0.9)},
            reports_present=_all_reports_present(),
            risk_decision=_approved_risk(),
            confidence_threshold=10.0,
            market_regime="bull_trend",
            critical_news_imminent=True,
        )
    )

    assert decision.state == "WAIT"
    assert "critical_news_imminent" in decision.uncertainty_factors


def test_missing_optional_report_does_not_force_wait() -> None:
    reports = _all_reports_present()
    reports["macro"] = False
    reports["news"] = False

    decision = evaluate(
        ChiefAIInput(
            department_votes={"technical": _vote(0.9, 0.05, 0.05, confidence=0.9)},
            reports_present=reports,
            risk_decision=_approved_risk(),
            confidence_threshold=10.0,
            market_regime="bull_trend",
            optional_reports=frozenset({"macro", "news"}),
        )
    )

    assert decision.state == "BUY"
    assert decision.is_reduced_confidence is True
    assert "reduced_confidence:macro_unavailable" in decision.reduced_confidence_factors
    assert "reduced_confidence:news_unavailable" in decision.reduced_confidence_factors


def test_missing_non_optional_report_still_forces_wait() -> None:
    reports = _all_reports_present()
    reports["macro"] = False
    reports["ml"] = False

    decision = evaluate(
        ChiefAIInput(
            department_votes={"technical": _vote(0.9, 0.05, 0.05, confidence=0.9)},
            reports_present=reports,
            risk_decision=_approved_risk(),
            market_regime="bull_trend",
            optional_reports=frozenset({"macro"}),
        )
    )

    assert decision.state == "WAIT"
    assert "required_report_missing" in decision.reasons
    assert any(factor.startswith("missing_report:ml") for factor in decision.uncertainty_factors)
    assert not any(
        factor.startswith("missing_report:macro") for factor in decision.uncertainty_factors
    )


def test_reduced_confidence_discounts_confidence_score() -> None:
    votes = {"technical": _vote(0.9, 0.05, 0.05, confidence=0.9)}
    full_reports = _all_reports_present()
    reduced_reports = _all_reports_present()
    reduced_reports["macro"] = False

    full_decision = evaluate(
        ChiefAIInput(
            department_votes=votes,
            reports_present=full_reports,
            risk_decision=_approved_risk(),
            confidence_threshold=10.0,
            market_regime="bull_trend",
        )
    )
    reduced_decision = evaluate(
        ChiefAIInput(
            department_votes=votes,
            reports_present=reduced_reports,
            risk_decision=_approved_risk(),
            confidence_threshold=10.0,
            market_regime="bull_trend",
            optional_reports=frozenset({"macro"}),
        )
    )

    assert reduced_decision.confidence_pct < full_decision.confidence_pct


def test_is_reduced_confidence_is_false_when_nothing_missing() -> None:
    decision = evaluate(
        ChiefAIInput(
            department_votes={"technical": _vote(0.9, 0.05, 0.05, confidence=0.9)},
            reports_present=_all_reports_present(),
            risk_decision=_approved_risk(),
            confidence_threshold=10.0,
            market_regime="bull_trend",
            optional_reports=frozenset({"macro", "news"}),
        )
    )

    assert decision.is_reduced_confidence is False
    assert decision.reduced_confidence_factors == []
