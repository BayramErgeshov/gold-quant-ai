"""Unit tests for department performance analysis."""

from __future__ import annotations

import uuid

import pytest

from src.engines.learning_engine.department_performance import compute_department_reliability
from src.models.trade import Trade

pytestmark = pytest.mark.unit


def _closed_trade(
    *, direction: str, realized_pnl: float, department_votes: dict[str, dict[str, object]] | None
) -> Trade:
    return Trade(
        symbol_id=uuid.uuid4(),
        direction=direction,
        status="closed",
        volume=1.0,
        entry_price=2000.0,
        stop_loss=1990.0,
        magic_number=1,
        realized_pnl=realized_pnl,
        department_votes=department_votes,
    )


def test_every_known_department_is_absent_when_no_trades_have_department_votes() -> None:
    # Per the "Performance Validation Framework" production requirement:
    # every known opinion department gets an entry (even zero-activity
    # ones), so `false_negative_rate` honestly reflects a department that
    # never voted, rather than silently omitting it.
    trades = [_closed_trade(direction="buy", realized_pnl=10.0, department_votes=None)]

    result = compute_department_reliability(trades)

    assert result["technical"].total_calls == 0
    assert result["technical"].false_negative_rate == pytest.approx(1.0)


def test_department_agreeing_with_a_winning_trade_is_correct() -> None:
    trades = [
        _closed_trade(
            direction="buy",
            realized_pnl=10.0,
            department_votes={"technical": {"bias": "bullish", "confidence": 0.8}},
        )
    ]

    result = compute_department_reliability(trades)

    assert result["technical"].total_calls == 1
    assert result["technical"].correct_calls == 1
    assert result["technical"].accuracy == 1.0


def test_department_agreeing_with_a_losing_trade_is_incorrect() -> None:
    trades = [
        _closed_trade(
            direction="buy",
            realized_pnl=-10.0,
            department_votes={"technical": {"bias": "bullish", "confidence": 0.8}},
        )
    ]

    result = compute_department_reliability(trades)

    assert result["technical"].correct_calls == 0
    assert result["technical"].accuracy == 0.0


def test_department_disagreeing_with_a_losing_trade_is_correct() -> None:
    # The trade bought and lost (price fell); a department that predicted
    # bearish correctly called the direction price actually moved.
    trades = [
        _closed_trade(
            direction="buy",
            realized_pnl=-10.0,
            department_votes={"correlation": {"bias": "bearish", "confidence": 0.5}},
        )
    ]

    result = compute_department_reliability(trades)

    assert result["correlation"].correct_calls == 1


def test_neutral_votes_are_not_counted_as_directional_calls() -> None:
    trades = [
        _closed_trade(
            direction="buy",
            realized_pnl=10.0,
            department_votes={"news": {"bias": "neutral", "confidence": 0.0}},
        )
    ]

    result = compute_department_reliability(trades)

    # Present but neutral: not a directional call, and not a "false
    # negative" either -- the department did have its say this cycle.
    assert result["news"].total_calls == 0
    assert result["news"].false_negative_rate == 0.0
    # A department entirely absent from this trade's snapshot, by contrast,
    # is a genuine gap.
    assert result["technical"].false_negative_rate == pytest.approx(1.0)


def test_trades_with_unknown_outcome_are_skipped() -> None:
    trades = [
        _closed_trade(
            direction="buy",
            realized_pnl=10.0,
            department_votes={"technical": {"bias": "bullish", "confidence": 0.8}},
        )
    ]
    trades[0].realized_pnl = None

    result = compute_department_reliability(trades)

    assert result["technical"].total_calls == 0
    assert result["technical"].false_negative_rate == 0.0


def test_reliability_defaults_to_neutral_below_minimum_sample_size() -> None:
    trades = [
        _closed_trade(
            direction="buy",
            realized_pnl=10.0,
            department_votes={"technical": {"bias": "bullish", "confidence": 0.8}},
        )
        for _ in range(5)
    ]

    result = compute_department_reliability(trades)

    assert result["technical"].total_calls == 5
    assert result["technical"].accuracy == 1.0
    assert result["technical"].reliability_score == 1.0  # still the neutral default


def test_reliability_equals_accuracy_at_or_above_minimum_sample_size() -> None:
    winning_trades = [
        _closed_trade(
            direction="buy",
            realized_pnl=10.0,
            department_votes={"technical": {"bias": "bullish", "confidence": 0.8}},
        )
        for _ in range(7)
    ]
    losing_trades = [
        _closed_trade(
            direction="buy",
            realized_pnl=-10.0,
            department_votes={"technical": {"bias": "bullish", "confidence": 0.8}},
        )
        for _ in range(3)
    ]

    result = compute_department_reliability(winning_trades + losing_trades)

    assert result["technical"].total_calls == 10
    assert result["technical"].accuracy == pytest.approx(0.7)
    assert result["technical"].reliability_score == pytest.approx(0.7)


def test_tracks_multiple_departments_independently() -> None:
    trades = [
        _closed_trade(
            direction="buy",
            realized_pnl=10.0,
            department_votes={
                "technical": {"bias": "bullish", "confidence": 0.8},
                "correlation": {"bias": "bearish", "confidence": 0.4},
            },
        )
    ]

    result = compute_department_reliability(trades)

    assert result["technical"].correct_calls == 1
    assert result["correlation"].correct_calls == 0


def test_department_agreeing_with_the_trade_direction_on_a_win_contributes_to_the_win() -> None:
    trades = [
        _closed_trade(
            direction="buy",
            realized_pnl=10.0,
            department_votes={"technical": {"bias": "bullish", "confidence": 0.8}},
        )
    ]

    result = compute_department_reliability(trades)

    assert result["technical"].win_contribution_rate == pytest.approx(1.0)
    assert result["technical"].loss_contribution_rate == 0.0
    assert result["technical"].false_positive_rate == 0.0


def test_department_agreeing_with_the_trade_direction_on_a_loss_contributes_to_the_loss() -> None:
    # A buy that loses moved down; a bullish vote agreed with the (losing)
    # buy direction, so it contributed to the loss and was itself wrong.
    trades = [
        _closed_trade(
            direction="buy",
            realized_pnl=-10.0,
            department_votes={"technical": {"bias": "bullish", "confidence": 0.8}},
        )
    ]

    result = compute_department_reliability(trades)

    assert result["technical"].loss_contribution_rate == pytest.approx(1.0)
    assert result["technical"].win_contribution_rate == 0.0
    assert result["technical"].false_positive_rate == pytest.approx(1.0)


def test_department_disagreeing_with_a_losing_trade_does_not_contribute_to_the_loss() -> None:
    # A buy that loses moved down; a bearish vote correctly called that
    # drop even though the trade itself (a buy) lost -- it warned against
    # the losing direction, so it must not be blamed for the loss.
    trades = [
        _closed_trade(
            direction="buy",
            realized_pnl=-10.0,
            department_votes={"technical": {"bias": "bearish", "confidence": 0.8}},
        )
    ]

    result = compute_department_reliability(trades)

    assert result["technical"].loss_contribution_rate == 0.0
    assert result["technical"].accuracy == pytest.approx(1.0)
    assert result["technical"].false_positive_rate == 0.0
