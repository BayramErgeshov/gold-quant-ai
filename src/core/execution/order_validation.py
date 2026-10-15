"""Pre-execution order validation for the Execution Engine.

Per MT5_ENGINE.md "Execution Validation" and "Account Safety": "Never
execute if Account Type Unknown, Account Number Changed, Live Account Not
Approved, Incorrect Symbol, Risk Engine Rejected, Chief AI Rejected."
Every check is explicit; the gateway never assumes any of these are satisfied.
"""

from __future__ import annotations

from dataclasses import dataclass, field

_KNOWN_ACCOUNT_TYPES: frozenset[str] = frozenset({"demo", "paper", "forward_test", "live"})


@dataclass(frozen=True, slots=True)
class ExecutionValidationRequest:
    """Every input the pre-execution safety gate checks.

    Attributes:
        expected_symbol: The symbol the trade was analyzed for.
        order_symbol: The symbol the order is about to be placed on.
        expected_account: The account number the platform expects to trade on.
        actual_account: The account number the connected terminal reports.
        account_type: One of "demo"/"paper"/"forward_test"/"live".
        live_trading_approved: Whether the user has explicitly enabled Live
            Mode (MT5_ENGINE.md "Initial Mode": "Live Mode is disabled" by default).
        is_terminal_connected: Whether the MT5 terminal connection is alive.
        is_market_open: Whether the relevant session is currently open.
        risk_approved: The Risk Engine's approval for this trade.
        chief_ai_approved: Whether the Chief AI's decision was BUY/SELL for this trade.
    """

    expected_symbol: str
    order_symbol: str
    expected_account: str | None
    actual_account: str | None
    account_type: str
    live_trading_approved: bool
    is_terminal_connected: bool
    is_market_open: bool
    risk_approved: bool
    chief_ai_approved: bool


@dataclass(frozen=True, slots=True)
class ExecutionValidationResult:
    """The outcome of the pre-execution safety gate.

    Attributes:
        approved: True only if every check passed.
        rejection_reasons: Every rule that failed. Empty if `approved`.
    """

    approved: bool
    rejection_reasons: list[str] = field(default_factory=list)


def validate_execution(request: ExecutionValidationRequest) -> ExecutionValidationResult:
    """Run the MT5_ENGINE.md "Account Safety" / "Execution Validation" checks.

    Args:
        request: Every input needed to evaluate the order.

    Returns:
        An `ExecutionValidationResult`. Never approves execution with any
        outstanding rejection reason.
    """
    reasons: list[str] = []

    if request.account_type not in _KNOWN_ACCOUNT_TYPES:
        reasons.append(f"account_type_unknown: {request.account_type!r}")
    if request.expected_account is not None and request.expected_account != request.actual_account:
        reasons.append(
            f"account_number_changed: expected {request.expected_account!r}, "
            f"got {request.actual_account!r}"
        )
    if request.account_type == "live" and not request.live_trading_approved:
        reasons.append("live_account_not_approved")
    if request.order_symbol != request.expected_symbol:
        reasons.append(
            f"incorrect_symbol: expected {request.expected_symbol!r}, got {request.order_symbol!r}"
        )
    if not request.is_terminal_connected:
        reasons.append("terminal_not_connected")
    if not request.is_market_open:
        reasons.append("market_closed")
    if not request.risk_approved:
        reasons.append("risk_engine_rejected")
    if not request.chief_ai_approved:
        reasons.append("chief_ai_rejected")

    return ExecutionValidationResult(approved=not reasons, rejection_reasons=reasons)
