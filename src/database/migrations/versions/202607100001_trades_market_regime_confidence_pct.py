"""Add market_regime and confidence_pct to trades.

Per the "Performance Validation Framework" production requirement:
"Profit by Market Regime" and "Profit by Confidence Range" need these
values captured at signal time, not recomputed later (recomputing regime
after the fact would use candles unavailable at the actual decision
moment).

Revision ID: 202607100001
Revises: 202607090005
Create Date: 2026-07-10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202607100001"
down_revision: str | None = "202607090005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("trades", sa.Column("market_regime", sa.String(length=30), nullable=True))
    op.add_column("trades", sa.Column("confidence_pct", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("trades", "confidence_pct")
    op.drop_column("trades", "market_regime")
