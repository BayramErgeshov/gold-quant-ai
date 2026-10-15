"""Composite indexes for multi-column filter+sort query patterns (institutional audit finding).

Per an institutional audit: `market_regimes`, `historical_similarities`
and `trades` each have only single-column indexes, but their own
repositories (`market_regime_repository.current_regime()`/
`list_by_symbol()`, `historical_similarity_repository.list_for_query()`,
`trade_repository.list_open()`) filter/sort on multiple of those columns
together. `candles` was also reviewed: its existing
`uq_candles_symbol_timeframe_timestamp` unique constraint already *is* a
composite `(symbol_id, timeframe, timestamp)` index PostgreSQL can use
for `CandleRepository.list_most_recent()`'s identical filter+sort shape,
so no new index is added there — this migration only adds indexes that
were genuinely missing.

Revision ID: 202607080004
Revises: 202607080003
Create Date: 2026-07-08
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "202607080004"
down_revision: str | None = "202607080003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_market_regimes_symbol_timeframe_start",
        "market_regimes",
        ["symbol_id", "timeframe", "start_timestamp"],
    )
    op.create_index(
        "ix_historical_similarities_symbol_timeframe_query",
        "historical_similarities",
        ["symbol_id", "timeframe", "query_timestamp"],
    )
    op.create_index("ix_trades_status_opened_at", "trades", ["status", "opened_at"])


def downgrade() -> None:
    op.drop_index("ix_trades_status_opened_at", table_name="trades")
    op.drop_index(
        "ix_historical_similarities_symbol_timeframe_query",
        table_name="historical_similarities",
    )
    op.drop_index("ix_market_regimes_symbol_timeframe_start", table_name="market_regimes")
