"""Unit tests for pre-execution order validation."""

from __future__ import annotations

import pytest

from src.core.execution.order_validation import ExecutionValidationRequest, validate_execution

pytestmark = pytest.mark.unit


def _base_request(**overrides: object) -> ExecutionValidationRequest:
    defaults: dict[str, object] = {
        "expected_symbol": "XAUUSD",
        "order_symbol": "XAUUSD",
        "expected_account": "12345",
        "actual_account": "12345",
        "account_type": "demo",
        "live_trading_approved": False,
        "is_terminal_connected": True,
        "is_market_open": True,
        "risk_approved": True,
        "chief_ai_approved": True,
    }
    defaults.update(overrides)
    return ExecutionValidationRequest(**defaults)  # type: ignore[arg-type]


def test_fully_valid_request_is_approved() -> None:
    result = validate_execution(_base_request())

    assert result.approved is True
    assert result.rejection_reasons == []


def test_unknown_account_type_is_rejected() -> None:
    result = validate_execution(_base_request(account_type="mystery"))

    assert result.approved is False
    assert any("account_type_unknown" in reason for reason in result.rejection_reasons)


def test_account_number_changed_is_rejected() -> None:
    result = validate_execution(_base_request(actual_account="99999"))

    assert result.approved is False
    assert any("account_number_changed" in reason for reason in result.rejection_reasons)


def test_expected_account_none_skips_account_check() -> None:
    result = validate_execution(_base_request(expected_account=None, actual_account="99999"))

    assert result.approved is True


def test_live_account_without_approval_is_rejected() -> None:
    result = validate_execution(_base_request(account_type="live", live_trading_approved=False))

    assert result.approved is False
    assert "live_account_not_approved" in result.rejection_reasons


def test_live_account_with_approval_is_not_rejected_for_that_reason() -> None:
    result = validate_execution(_base_request(account_type="live", live_trading_approved=True))

    assert "live_account_not_approved" not in result.rejection_reasons


def test_incorrect_symbol_is_rejected() -> None:
    result = validate_execution(_base_request(order_symbol="EURUSD"))

    assert result.approved is False
    assert any("incorrect_symbol" in reason for reason in result.rejection_reasons)


def test_disconnected_terminal_is_rejected() -> None:
    result = validate_execution(_base_request(is_terminal_connected=False))

    assert result.approved is False
    assert "terminal_not_connected" in result.rejection_reasons


def test_closed_market_is_rejected() -> None:
    result = validate_execution(_base_request(is_market_open=False))

    assert result.approved is False
    assert "market_closed" in result.rejection_reasons


def test_risk_rejection_is_reported() -> None:
    result = validate_execution(_base_request(risk_approved=False))

    assert result.approved is False
    assert "risk_engine_rejected" in result.rejection_reasons


def test_chief_ai_rejection_is_reported() -> None:
    result = validate_execution(_base_request(chief_ai_approved=False))

    assert result.approved is False
    assert "chief_ai_rejected" in result.rejection_reasons


def test_multiple_failures_are_all_reported() -> None:
    result = validate_execution(_base_request(is_market_open=False, risk_approved=False))

    assert result.approved is False
    assert len(result.rejection_reasons) == 2
