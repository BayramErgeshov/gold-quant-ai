"""Position reconciliation: MT5 vs. the trade journal (institutional audit finding).

Per an institutional audit: this platform never checked, on startup or
periodically, whether MT5's actual open positions match the trade
journal's `status="open"` rows. A process crash, DB connection loss, or
any other failure between order placement and journal commit can leave
the two silently diverged — the exact failure class already found and
fixed once this session (a Telegram notification exception rolling back
a just-written trade journal entry for a real, already-placed order).

This module only detects and reports mismatches. Per this platform's own
governance principle — no automatic correction of financial state without
human review, the same principle already applied in
`src.engines.learning_engine.department_performance` ("measure only,
never auto-applied") — it never modifies MT5 or the journal itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.core.execution.mt5_client import MT5Client
from src.repositories.trade_repository import TradeRepository

_MAX_OPEN_TRADES_CHECKED = 1000


@dataclass(frozen=True, slots=True)
class ReconciliationReport:
    """Mismatches found between MT5's real open positions and the trade journal.

    Attributes:
        broker_tickets_missing_from_journal: Open on MT5 but with no
            corresponding `status="open"` journal row — a real position
            with no journal record (e.g. lost after a mid-cycle crash).
        journal_trades_missing_from_broker: Journaled as `status="open"`
            but MT5 reports no matching open position — likely closed
            manually, or by another process, without the journal being updated.
        matched_count: Broker tickets present and consistent on both sides.
    """

    broker_tickets_missing_from_journal: list[str] = field(default_factory=list)
    journal_trades_missing_from_broker: list[str] = field(default_factory=list)
    matched_count: int = 0

    @property
    def is_clean(self) -> bool:
        """Whether every open position/journal row matched with no discrepancy."""
        return not self.broker_tickets_missing_from_journal and (
            not self.journal_trades_missing_from_broker
        )


async def reconcile_positions(
    *, mt5_client: MT5Client, trade_repository: TradeRepository, mt5_symbol: str
) -> ReconciliationReport:
    """Compare MT5's real open positions against the trade journal's "open" rows.

    Args:
        mt5_client: Execution gateway to read real open positions from.
        trade_repository: Source of truth for journaled trades.
        mt5_symbol: Broker symbol to scope the comparison to.

    Returns:
        A `ReconciliationReport` of every mismatch found. Never modifies
        MT5 or the journal — flags discrepancies for human review only.
    """
    broker_positions = await mt5_client.get_open_positions(symbol=mt5_symbol)
    broker_tickets = {position.ticket for position in broker_positions}

    journaled_open_trades = await trade_repository.list_by_status(
        "open", limit=_MAX_OPEN_TRADES_CHECKED
    )
    journaled_tickets = {
        trade.broker_ticket for trade in journaled_open_trades if trade.broker_ticket is not None
    }

    return ReconciliationReport(
        broker_tickets_missing_from_journal=sorted(broker_tickets - journaled_tickets),
        journal_trades_missing_from_broker=sorted(journaled_tickets - broker_tickets),
        matched_count=len(broker_tickets & journaled_tickets),
    )
