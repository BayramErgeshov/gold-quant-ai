"""One-off historical backfill script: downloads XAUUSD candles directly
from a live MT5 terminal across multiple timeframes and stores them via
`MT5HistoricalIngestionService`.

Run with the project's own virtual environment interpreter:

    ./.venv/Scripts/python.exe scripts/mt5_historical_backfill.py

Credentials (MT5_LOGIN/MT5_PASSWORD/MT5_SERVER) and POSTGRES_PASSWORD are
read from the environment, never hardcoded. Read/write to the database
only — never places an order or modifies any account state.

The Windows event loop policy must be set before *any* other import that
might create a default event loop (e.g. via an eager `asyncio.get_event_loop()`
call somewhere in the dependency chain) — see
`src.core.execution.mt5_client`'s module docstring for why. That import
and call therefore happen first, deliberately ahead of every other import.
"""

from __future__ import annotations

import asyncio
import sys

from src.core.execution.mt5_client import configure_event_loop_policy

configure_event_loop_policy()

from src.core.execution.mt5_client import RealMT5Client  # noqa: E402
from src.database.postgres.session import get_session  # noqa: E402
from src.engines.historical_engine.mt5_ingestion import MT5HistoricalIngestionService  # noqa: E402
from src.repositories.candle_repository import CandleRepository  # noqa: E402
from src.repositories.symbol_repository import SymbolRepository  # noqa: E402

_TIMEFRAMES_AND_COUNTS: list[tuple[str, int]] = [
    ("M15", 5000),
    ("H1", 3000),
    ("H4", 2000),
    ("D1", 1500),
]


async def main() -> int:
    mt5_client = RealMT5Client()
    connected = await mt5_client.connect()
    print(f"MT5 connected: {connected}")
    if not connected:
        print("Connection failed; run scripts/mt5_connection_check.py for details.")
        return 1

    async with get_session() as session:
        symbol = await SymbolRepository(session).get_by_name("XAUUSD")
        if symbol is None:
            print("FAILED: XAUUSD symbol not seeded. Run seed_primary_symbol first.")
            return 1
        print(f"symbol: {symbol.id}")

        service = MT5HistoricalIngestionService(
            candle_repository=CandleRepository(session), mt5_client=mt5_client
        )
        for timeframe, count in _TIMEFRAMES_AND_COUNTS:
            result = await service.ingest(
                symbol.id, mt5_symbol="XAUUSD", timeframe=timeframe, count=count
            )
            print(
                f"{timeframe}: requested={result.requested} valid={result.valid} "
                f"inserted={result.inserted} issues={len(result.issues)}"
            )

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
