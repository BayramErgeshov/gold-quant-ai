"""Historical candle ingestion service.

Per HISTORICAL_RESEARCH_ENGINE.md ("On first startup... Download maximum
available XAUUSD history... Normalize, Validate, Store") and
DATA_COLLECTION_ENGINE.md. MT5 itself (a Tier 1 source) requires a running
terminal and broker credentials not available in this environment; this
service uses the Tier 2 `TwelveDataMarketProvider` (Phase 3) through the
standard `FallbackChain`, so it activates automatically once
`TWELVEDATA_API_KEY` is added to `.env` — no code changes needed. Adding an
MT5-backed Tier 1 provider later only means adding it to the provider list
passed to `FallbackChain` (DATA_COLLECTION_ENGINE.md's provider architecture).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from src.common.logging import get_logger
from src.core.data_collection.cache import build_cache_key
from src.core.data_collection.fallback import FallbackChain
from src.core.data_collection.models import SourceCategory
from src.engines.historical_engine.validation import ValidationIssue, validate_candles
from src.models.candle import Candle
from src.repositories.candle_repository import CandleRepository
from src.services.market.providers.twelvedata_provider import TwelveDataMarketProvider
from src.settings import Settings, get_settings

logger = get_logger(__name__)

_TWELVEDATA_INTERVAL_BY_TIMEFRAME: dict[str, str] = {
    "M1": "1min",
    "M5": "5min",
    "M15": "15min",
    "M30": "30min",
    "H1": "1h",
    "H4": "4h",
    "D1": "1day",
    "W1": "1week",
    "MN": "1month",
}
_DATA_CATEGORY = SourceCategory.MARKET_DATA


@dataclass(frozen=True, slots=True)
class IngestionResult:
    """Outcome of a single historical ingestion run.

    Attributes:
        requested: Number of candles returned by the provider/cache.
        valid: Number that passed validation.
        inserted: Number newly inserted (excludes already-stored candles).
        issues: Every validation issue found.
    """

    requested: int
    valid: int
    inserted: int
    issues: list[ValidationIssue]


def _parse_twelvedata_datetime(raw: str) -> datetime:
    """Parse a TwelveData timestamp string (daily "YYYY-MM-DD" or
    intraday "YYYY-MM-DD HH:MM:SS") into a UTC-aware `datetime`."""
    fmt = "%Y-%m-%d %H:%M:%S" if " " in raw else "%Y-%m-%d"
    return datetime.strptime(raw, fmt).replace(tzinfo=UTC)


def _to_candle(
    symbol_id: uuid.UUID, timeframe: str, raw: dict[str, Any], *, source: str
) -> Candle:
    """Convert a single TwelveData candle record into a `Candle` ORM instance."""
    volume = raw.get("volume")
    return Candle(
        symbol_id=symbol_id,
        timeframe=timeframe,
        timestamp=_parse_twelvedata_datetime(raw["datetime"]),
        open=float(raw["open"]),
        high=float(raw["high"]),
        low=float(raw["low"]),
        close=float(raw["close"]),
        volume=float(volume) if volume is not None else None,
        source=source,
    )


class HistoricalIngestionService:
    """Downloads, validates and stores historical candles for a symbol."""

    def __init__(
        self,
        *,
        candle_repository: CandleRepository,
        settings: Settings | None = None,
        fallback_chain: FallbackChain[list[dict[str, Any]]] | None = None,
    ) -> None:
        """Initialize the service.

        Args:
            candle_repository: Persists validated candles.
            settings: Application settings. Defaults to `get_settings()`.
            fallback_chain: Provider chain to fetch candles from. Defaults
                to a chain containing only `TwelveDataMarketProvider`;
                injectable for testing and for adding higher-tier
                providers (e.g. MT5) later.
        """
        resolved_settings = settings or get_settings()
        self._candles = candle_repository
        self._fallback_chain = fallback_chain or FallbackChain(
            [TwelveDataMarketProvider(resolved_settings)], category=_DATA_CATEGORY
        )

    async def ingest(
        self,
        symbol_id: uuid.UUID,
        *,
        provider_symbol: str,
        timeframe: str,
        output_size: int = 5000,
    ) -> IngestionResult:
        """Download, validate and store historical candles for one symbol/timeframe.

        Args:
            symbol_id: The platform `Symbol` id candles belong to.
            provider_symbol: The symbol name as understood by the data
                provider, e.g. "XAU/USD" for TwelveData.
            timeframe: One of `src.models.candle.TIMEFRAMES`.
            output_size: Number of most recent candles to request.

        Returns:
            An `IngestionResult` summarizing what was fetched, validated
            and stored.

        Raises:
            ValueError: If `timeframe` has no known provider interval mapping.
            src.core.data_collection.exceptions.AllProvidersFailedError:
                If no provider is configured/reachable and nothing is cached
                (e.g. `TWELVEDATA_API_KEY` is not set yet) — never
                fabricated as empty/fake data.
        """
        interval = _TWELVEDATA_INTERVAL_BY_TIMEFRAME.get(timeframe)
        if interval is None:
            raise ValueError(f"Unsupported timeframe for historical ingestion: {timeframe!r}")

        cache_key = build_cache_key(
            _DATA_CATEGORY.value, f"twelvedata:{provider_symbol}:{interval}"
        )
        dataset = await self._fallback_chain.fetch(
            cache_key, symbol=provider_symbol, interval=interval, output_size=output_size
        )

        candles = [
            _to_candle(symbol_id, timeframe, raw, source=dataset.metadata.source)
            for raw in dataset.data
        ]
        report = validate_candles(candles, timeframe=timeframe)
        for issue in report.issues:
            logger.warning(
                "historical_candle_issue",
                kind=issue.kind,
                detail=issue.detail,
                timestamp=str(issue.timestamp),
            )

        inserted = await self._candles.insert_new(report.valid_candles)
        logger.info(
            "historical_ingestion_completed",
            symbol_id=str(symbol_id),
            timeframe=timeframe,
            requested=len(candles),
            valid=len(report.valid_candles),
            inserted=inserted,
        )
        return IngestionResult(
            requested=len(candles),
            valid=len(report.valid_candles),
            inserted=inserted,
            issues=report.issues,
        )
