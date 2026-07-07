"""Historical candle data validation.

Per DATA_QUALITY_STANDARD.md ("Every candle must contain... Validation
Status") and DATA_COLLECTION_ENGINE.md ("Never store duplicates... Detect
Missing Data, Incorrect Values, Duplicate Records"). Every batch of
candles is checked for OHLC integrity, in-batch duplicates and gaps before
storage. Invalid candles are reported and excluded — never silently
"fixed" or fabricated (DATA_QUALITY_STANDARD.md: "Never fabricate missing
values").
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from src.models.candle import Candle

TIMEFRAME_INTERVALS: dict[str, timedelta] = {
    "M1": timedelta(minutes=1),
    "M5": timedelta(minutes=5),
    "M15": timedelta(minutes=15),
    "M30": timedelta(minutes=30),
    "H1": timedelta(hours=1),
    "H4": timedelta(hours=4),
    "D1": timedelta(days=1),
    "W1": timedelta(weeks=1),
    # "MN" (monthly) intervals vary (28-31 days); gap detection is skipped
    # for it rather than using a misleading fixed approximation.
}

_GAP_TOLERANCE_MULTIPLIER = 1.5


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """A single data quality problem found in a candle batch.

    Attributes:
        kind: One of "duplicate_timestamp", "invalid_ohlc",
            "negative_value", "gap".
        detail: Human-readable explanation.
        timestamp: The affected candle's timestamp, if applicable.
    """

    kind: str
    detail: str
    timestamp: datetime | None = None


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """Outcome of validating a batch of candles.

    Attributes:
        issues: Every problem found, in the order encountered.
        valid_candles: Candles that passed integrity checks, sorted by
            timestamp and with in-batch duplicates removed. Gaps are
            reported but do not exclude the candle that follows the gap.
    """

    issues: list[ValidationIssue]
    valid_candles: list[Candle]

    @property
    def is_clean(self) -> bool:
        """True if no issues were found at all."""
        return not self.issues


def _check_ohlc_integrity(candle: Candle) -> ValidationIssue | None:
    """Check a single candle's OHLC relationships and value ranges."""
    if candle.open <= 0 or candle.high <= 0 or candle.low <= 0 or candle.close <= 0:
        return ValidationIssue("negative_value", "non-positive price", candle.timestamp)
    if candle.volume is not None and candle.volume < 0:
        return ValidationIssue("negative_value", "negative volume", candle.timestamp)
    if candle.high < candle.low:
        return ValidationIssue("invalid_ohlc", "high < low", candle.timestamp)
    if candle.high < candle.open or candle.high < candle.close:
        return ValidationIssue("invalid_ohlc", "high below open/close", candle.timestamp)
    if candle.low > candle.open or candle.low > candle.close:
        return ValidationIssue("invalid_ohlc", "low above open/close", candle.timestamp)
    return None


def validate_candles(candles: list[Candle], *, timeframe: str) -> ValidationReport:
    """Validate a batch of candles for integrity, duplicates and gaps.

    Args:
        candles: Candidate candles for a single symbol/timeframe.
        timeframe: The nominal timeframe all candles should conform to,
            used for gap detection (see `TIMEFRAME_INTERVALS`).

    Returns:
        A `ValidationReport` listing every issue found and the candles
        that passed integrity checks.
    """
    issues: list[ValidationIssue] = []
    valid_candles: list[Candle] = []
    seen_timestamps: set[datetime] = set()
    expected_interval = TIMEFRAME_INTERVALS.get(timeframe)
    previous_timestamp: datetime | None = None

    for candle in sorted(candles, key=lambda item: item.timestamp):
        if candle.timestamp in seen_timestamps:
            issues.append(
                ValidationIssue("duplicate_timestamp", "duplicate within batch", candle.timestamp)
            )
            continue
        seen_timestamps.add(candle.timestamp)

        integrity_issue = _check_ohlc_integrity(candle)
        if integrity_issue is not None:
            issues.append(integrity_issue)
            continue

        if previous_timestamp is not None and expected_interval is not None:
            gap = candle.timestamp - previous_timestamp
            if gap > expected_interval * _GAP_TOLERANCE_MULTIPLIER:
                issues.append(ValidationIssue("gap", f"gap of {gap}", candle.timestamp))

        valid_candles.append(candle)
        previous_timestamp = candle.timestamp

    return ValidationReport(issues=issues, valid_candles=valid_candles)
