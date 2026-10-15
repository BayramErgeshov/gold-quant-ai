"""Phase 23 Claim Validation entrypoint.

Runs `ClaimValidationService` once against the primary symbol's stored
candle history, validating every pending `BookClaim` extracted by the
Book Engine. Intended to run on a schedule (e.g. daily, after new books
have been ingested) alongside `scripts/run_books_watcher.py`, per the
Institutional Knowledge Research System spec: "Every extracted hypothesis
auto-enters the Research Engine... without requiring user interaction."

Run with the project's own virtual environment interpreter:

    PYTHONPATH=. POSTGRES_PASSWORD=changeme \\
        ./.venv/Scripts/python.exe scripts/run_claim_validation.py
"""

from __future__ import annotations

import asyncio
import sys

from src.common.logging import get_logger
from src.database.postgres.session import get_session
from src.engines.book_engine.claim_validation import ClaimValidationService
from src.repositories.book_claim_repository import BookClaimRepository
from src.repositories.candle_repository import CandleRepository
from src.repositories.symbol_repository import SymbolRepository
from src.settings import get_settings

logger = get_logger(__name__)

_TIMEFRAME = "H1"
_CANDLE_HISTORY_COUNT = 5000


async def main() -> int:
    settings = get_settings()
    mt5_symbol = settings.platform.symbols.primary

    async with get_session() as session:
        symbol = await SymbolRepository(session).get_by_name(mt5_symbol)
        if symbol is None:
            logger.error("claim_validation_startup_failed", reason="symbol_not_seeded")
            return 1

        candles = await CandleRepository(session).list_most_recent(
            symbol.id, _TIMEFRAME, count=_CANDLE_HISTORY_COUNT
        )
        if not candles:
            logger.error(
                "claim_validation_startup_failed",
                reason="no_candle_history",
                timeframe=_TIMEFRAME,
            )
            return 1

        service = ClaimValidationService(claim_repository=BookClaimRepository(session))
        results = await service.validate_pending_claims(candles)

    accepted = sum(1 for result in results if result.status == "accepted")
    rejected = sum(1 for result in results if result.status == "rejected")
    unknown = sum(1 for result in results if result.status == "unknown")
    logger.info(
        "claim_validation_completed",
        processed=len(results),
        accepted=accepted,
        rejected=rejected,
        unknown=unknown,
    )
    print(
        f"Processed {len(results)} claims: "
        f"{accepted} accepted, {rejected} rejected, {unknown} unknown."
    )
    for result in results:
        print(f"  {result.status:8s} claim={result.claim_id} {result.reason}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
