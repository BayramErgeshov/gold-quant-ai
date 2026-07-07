"""Historical candle ingestion directly from a live MT5 terminal.

Per HISTORICAL_RESEARCH_ENGINE.md ("On first startup... Download maximum
available XAUUSD history... Normalize, Validate, Store") and Phase 20's
reduced-mode deployment (PROJECT_VISION.md continuous-improvement
principle applied pragmatically): with a live MT5 terminal connected but
no TwelveData API key configured, MT5 itself becomes the historical data
source rather than blocking on an unconfigured provider. Reuses the same
validation pipeline as
`src.engines.historical_engine.ingestion.HistoricalIngestionService`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from src.common.logging import get_logger
from src.core.execution.mt5_client import MT5Client
from src.engines.historical_engine.validation import ValidationIssue, validate_candles
from src.models.candle import Candle
from src.repositories.candle_repository import CandleRepository

logger = get_logger(__name__)

_SOURCE_NAME = "mt5"


@dataclass(frozen=True, slots=True)
class MT5IngestionResult:
    """Outcome of a single MT5 historical ingestion run.

    Attributes:
        requested: Number of candles returned by MT5.
        valid: Number that passed validation.
        inserted: Number newly inserted (excludes already-stored candles).
        issues: Every validation issue found.
    """

    requested: int
    valid: int
    inserted: int
    issues: list[ValidationIssue]


def _to_candle(symbol_id: uuid.UUID, timeframe: str, raw: dict[str, Any]) -> Candle:
    """Convert a single MT5 bar dict into a `Candle` ORM instance."""
    return Candle(
        symbol_id=symbol_id,
        timeframe=timeframe,
        timestamp=datetime.fromtimestamp(raw["time"], tz=UTC),
        open=float(raw["open"]),
        high=float(raw["high"]),
        low=float(raw["low"]),
        close=float(raw["close"]),
        volume=float(raw["tick_volume"]),
        spread=float(raw["spread"]),
        source=_SOURCE_NAME,
    )


class MT5HistoricalIngestionService:
    """Downloads, validates and stores historical candles directly from MT5."""

    def __init__(self, *, candle_repository: CandleRepository, mt5_client: MT5Client) -> None:
        """Initialize the service (constructor injection).

        Args:
            candle_repository: Persists validated candles.
            mt5_client: Live MT5 gateway to fetch bars from.
        """
        self._candles = candle_repository
        self._mt5 = mt5_client

    async def ingest(
        self, symbol_id: uuid.UUID, *, mt5_symbol: str, timeframe: str, count: int = 5000
    ) -> MT5IngestionResult:
        """Download, validate and store historical candles for one symbol/timeframe.

        Args:
            symbol_id: The platform `Symbol` id candles belong to.
            mt5_symbol: The symbol name as known to the MT5 terminal, e.g. "XAUUSD".
            timeframe: One of `src.models.candle.TIMEFRAMES`.
            count: Number of most recent bars to request.

        Returns:
            An `MT5IngestionResult` summarizing what was fetched, validated
            and stored. `requested == 0` if MT5 returned no data for this
            symbol/timeframe — never a fabricated result.
        """
        raw_candles = await self._mt5.get_candles(mt5_symbol, timeframe, count)
        candles = [_to_candle(symbol_id, timeframe, raw) for raw in raw_candles]

        report = validate_candles(candles, timeframe=timeframe)
        for issue in report.issues:
            logger.warning(
                "mt5_historical_candle_issue",
                kind=issue.kind,
                detail=issue.detail,
                timestamp=str(issue.timestamp),
            )

        inserted = await self._candles.insert_new(report.valid_candles)
        logger.info(
            "mt5_historical_ingestion_completed",
            symbol_id=str(symbol_id),
            timeframe=timeframe,
            requested=len(candles),
            valid=len(report.valid_candles),
            inserted=inserted,
        )
        return MT5IngestionResult(
            requested=len(candles),
            valid=len(report.valid_candles),
            inserted=inserted,
            issues=report.issues,
        )
