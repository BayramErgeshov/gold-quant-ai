"""Telegram message formatting.

Per TELEGRAM.md "Message Rules": "Always include timestamp. Always
include confidence. Always include reason. Always include journal
reference. Always remain concise." Every formatter here builds Markdown
text purely from already-computed data — never inventing a field the
caller did not supply.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.models.improvement_proposal import ImprovementProposal
from src.models.news_article import NewsArticle
from src.models.trade import Trade


@dataclass(frozen=True, slots=True)
class SignalMessageData:
    """Fields for a Telegram "Signal Message" (TELEGRAM.md "Signal Message").

    Attributes:
        trade_id: Journal reference for this signal.
        timestamp: When the signal was generated.
        market: Symbol name, e.g. "XAUUSD".
        direction: "BUY" or "SELL".
        entry_price: Planned entry price.
        stop_loss: Protective stop price.
        targets: Ordered target prices (TP1, TP2, TP3, ...).
        confidence_pct: Overall decision confidence, 0-100.
        quality_grade: Institutional grade, e.g. "AA".
        reason_summary: Short evidence summary.
        alternative_scenario: The counter-scenario, if the primary is wrong.
        risk_summary: Short risk assessment.
    """

    trade_id: str
    timestamp: datetime
    market: str
    direction: str
    entry_price: float
    stop_loss: float
    targets: list[float]
    confidence_pct: float
    quality_grade: str
    reason_summary: str
    alternative_scenario: str
    risk_summary: str


def format_signal_message(data: SignalMessageData) -> str:
    """Format a Telegram "Signal Message".

    Args:
        data: The signal's fields.

    Returns:
        Concise Markdown text.
    """
    targets_line = ", ".join(f"{target:.2f}" for target in data.targets) or "N/A"
    return (
        f"*SIGNAL* — {data.market} {data.direction}\n"
        f"Time: {data.timestamp.isoformat()}\n"
        f"Entry: {data.entry_price:.2f} | Stop: {data.stop_loss:.2f} | Targets: {targets_line}\n"
        f"Confidence: {data.confidence_pct:.0f}% ({data.quality_grade})\n"
        f"Reason: {data.reason_summary}\n"
        f"Alternative: {data.alternative_scenario}\n"
        f"Risk: {data.risk_summary}\n"
        f"Journal: {data.trade_id}"
    )


def format_trade_closed_message(trade: Trade, *, prediction_accuracy: str | None = None) -> str:
    """Format a Telegram "Trade Closed Message" (TELEGRAM.md).

    Args:
        trade: The closed `Trade`.
        prediction_accuracy: Optional caller-supplied prediction-accuracy note.

    Returns:
        Concise Markdown text.

    Raises:
        ValueError: If `trade.entry_price` or `trade.exit_price` is missing.
    """
    if trade.entry_price is None or trade.exit_price is None:
        raise ValueError("A closed trade must have both entry_price and exit_price recorded")

    duration = (
        str(trade.closed_at - trade.opened_at)
        if trade.opened_at is not None and trade.closed_at is not None
        else "unknown"
    )
    result_label = "Profit" if (trade.realized_pnl or 0.0) >= 0 else "Loss"
    pnl_line = (
        f"{result_label}: {trade.realized_pnl:.2f}"
        if trade.realized_pnl is not None
        else "P/L: unknown"
    )
    lines = [
        f"*TRADE CLOSED* — {trade.direction.upper()}",
        f"Entry: {trade.entry_price:.2f} -> Exit: {trade.exit_price:.2f}",
        f"Duration: {duration}",
        pnl_line,
        f"Exit reason: {trade.error_message or trade.status}",
        f"Journal: {trade.id}",
    ]
    if prediction_accuracy is not None:
        lines.insert(-1, f"Prediction accuracy: {prediction_accuracy}")
    return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class DailyReportData:
    """Fields for a Telegram "Daily Report" (TELEGRAM.md "Daily Report").

    Attributes:
        report_date: The date this report covers.
        total_signals: Number of signals generated.
        executed_trades: Number of trades actually executed.
        winning_trades: Number of winning trades.
        losing_trades: Number of losing trades.
        win_rate: Fraction of executed trades that won.
        profit_factor: Gross profit / gross loss.
        net_result_pct: Net result, in percent.
        system_health: Short system-health note.
    """

    report_date: str
    total_signals: int
    executed_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    profit_factor: float
    net_result_pct: float
    system_health: str = "OK"


def format_daily_report(data: DailyReportData) -> str:
    """Format a Telegram "Daily Report".

    Args:
        data: The report's fields.

    Returns:
        Concise Markdown text.
    """
    return (
        f"*DAILY REPORT* — {data.report_date}\n"
        f"Signals: {data.total_signals} | Executed: {data.executed_trades}\n"
        f"Wins: {data.winning_trades} | Losses: {data.losing_trades} "
        f"(win rate {data.win_rate:.0%})\n"
        f"Profit factor: {data.profit_factor:.2f} | Net result: {data.net_result_pct:+.2f}%\n"
        f"System health: {data.system_health}"
    )


def format_news_alert(article: NewsArticle) -> str:
    """Format a Telegram "News Alert" (TELEGRAM.md).

    Args:
        article: The classified, scored `NewsArticle`.

    Returns:
        Concise Markdown text.
    """
    return (
        f"*NEWS ALERT* — {article.title}\n"
        f"Source: {article.source} | Importance: {article.importance_score:.2f}\n"
        f"Expected volatility: {article.expected_volatility}\n"
        f"Category: {article.category or 'unclassified'}"
    )


@dataclass(frozen=True, slots=True)
class ErrorReportData:
    """Fields for a Telegram "Error Report" (TELEGRAM.md "Error Report").

    Attributes:
        timestamp: When the error occurred.
        module: The module/component that raised it.
        error: A short error description.
        severity: One of "low", "medium", "high", "critical".
        automatic_recovery: Whether the system recovered automatically.
        manual_action_required: Whether a human must intervene.
        status: Current status, e.g. "resolved", "monitoring".
    """

    timestamp: datetime
    module: str
    error: str
    severity: str
    automatic_recovery: bool
    manual_action_required: bool
    status: str


def format_error_report(data: ErrorReportData) -> str:
    """Format a Telegram "Error Report".

    Args:
        data: The report's fields.

    Returns:
        Concise Markdown text.
    """
    return (
        f"*ERROR* [{data.severity.upper()}] — {data.module}\n"
        f"Time: {data.timestamp.isoformat()}\n"
        f"{data.error}\n"
        f"Auto-recovered: {'yes' if data.automatic_recovery else 'no'} | "
        f"Manual action required: {'yes' if data.manual_action_required else 'no'}\n"
        f"Status: {data.status}"
    )


def format_approval_request(proposal: ImprovementProposal) -> str:
    """Format a Telegram "Approval Request" (TELEGRAM.md "Approval Request").

    Args:
        proposal: The pending `ImprovementProposal`.

    Returns:
        Concise Markdown text ending with the Approve/Reject/Postpone
        choices the user must make (TELEGRAM.md: "The user receives...
        Approve, Reject, Postpone").
    """
    return (
        f"*APPROVAL REQUESTED* — {proposal.title}\n"
        f"Problem: {proposal.problem}\n"
        f"Evidence: {proposal.evidence}\n"
        f"Expected benefit: {proposal.expected_benefit}\n"
        f"Potential risk: {proposal.potential_risk}\n"
        f"Difficulty: {proposal.implementation_difficulty}\n"
        f"Recommendation: {proposal.recommendation}\n"
        f"Reply: Approve / Reject / Postpone (ref: {proposal.id})"
    )
