"""One-off backfill: downloads real historical OHLCV for every enabled
correlated instrument (`src.database.seed.seed_correlated_instruments`)
across the timeframes the Correlation Engine analyzes.

Run with the project's own virtual environment interpreter:

    PYTHONPATH=. ./.venv/Scripts/python.exe scripts/correlation_backfill.py
"""

from __future__ import annotations

import asyncio
import sys

from src.core.execution.mt5_client import RealMT5Client, configure_event_loop_policy
from src.database.postgres.session import get_session
from src.engines.correlation_engine.ingestion import CorrelatedInstrumentIngestionService
from src.repositories.correlated_instrument_repository import CorrelatedInstrumentRepository
from src.repositories.correlated_price_repository import CorrelatedPriceRepository

_TIMEFRAME_COUNTS: list[tuple[str, int]] = [("H1", 3000), ("H4", 2000), ("D1", 1500)]


async def main() -> int:
    configure_event_loop_policy()
    mt5_client = RealMT5Client()
    if not await mt5_client.connect():
        print("FAILED: could not connect to MT5")
        return 1

    async with get_session() as session:
        instruments = await CorrelatedInstrumentRepository(session).list_enabled_with_mt5_symbol()
        service = CorrelatedInstrumentIngestionService(
            price_repository=CorrelatedPriceRepository(session), mt5_client=mt5_client
        )
        for instrument in instruments:
            assert instrument.mt5_symbol is not None
            for timeframe, count in _TIMEFRAME_COUNTS:
                result = await service.ingest(
                    instrument.id,
                    mt5_symbol=instrument.mt5_symbol,
                    timeframe=timeframe,
                    count=count,
                )
                print(
                    f"{instrument.name} ({instrument.mt5_symbol}) {timeframe}: "
                    f"requested={result.requested} valid={result.valid} "
                    f"inserted={result.inserted} skipped={len(result.skipped_reasons)}"
                )

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
