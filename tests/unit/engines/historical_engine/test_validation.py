"""Unit tests for `src.engines.historical_engine.validation`."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from src.engines.historical_engine.validation import validate_candles
from src.models.candle import Candle

pytestmark = pytest.mark.unit

_SYMBOL_ID = uuid.uuid4()
_BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


def _candle(offset_hours: float, **overrides: object) -> Candle:
    defaults: dict[str, object] = {
        "symbol_id": _SYMBOL_ID,
        "timeframe": "H1",
        "timestamp": _BASE_TIME + timedelta(hours=offset_hours),
        "open": 3400.0,
        "high": 3405.0,
        "low": 3395.0,
        "close": 3402.0,
        "volume": 100.0,
        "source": "twelvedata",
    }
    defaults.update(overrides)
    return Candle(**defaults)  # type: ignore[arg-type]


def test_clean_batch_has_no_issues() -> None:
    report = validate_candles([_candle(0), _candle(1), _candle(2)], timeframe="H1")

    assert report.is_clean
    assert len(report.valid_candles) == 3


def test_detects_duplicate_timestamps_within_batch() -> None:
    report = validate_candles([_candle(0), _candle(0)], timeframe="H1")

    assert any(issue.kind == "duplicate_timestamp" for issue in report.issues)
    assert len(report.valid_candles) == 1


def test_detects_high_below_low() -> None:
    report = validate_candles([_candle(0, high=3390.0, low=3395.0)], timeframe="H1")

    assert any(issue.kind == "invalid_ohlc" for issue in report.issues)
    assert report.valid_candles == []


def test_detects_high_below_open_or_close() -> None:
    report = validate_candles([_candle(0, high=3398.0, open=3400.0)], timeframe="H1")

    assert any(issue.kind == "invalid_ohlc" for issue in report.issues)


def test_detects_low_above_open_or_close() -> None:
    report = validate_candles([_candle(0, low=3403.0, close=3402.0)], timeframe="H1")

    assert any(issue.kind == "invalid_ohlc" for issue in report.issues)


def test_detects_non_positive_prices() -> None:
    report = validate_candles([_candle(0, open=0.0)], timeframe="H1")

    assert any(issue.kind == "negative_value" for issue in report.issues)


def test_detects_negative_volume() -> None:
    report = validate_candles([_candle(0, volume=-5.0)], timeframe="H1")

    assert any(issue.kind == "negative_value" for issue in report.issues)


def test_detects_gap_exceeding_expected_interval() -> None:
    report = validate_candles([_candle(0), _candle(10)], timeframe="H1")

    gap_issues = [issue for issue in report.issues if issue.kind == "gap"]
    assert len(gap_issues) == 1
    # The candle after the gap is still included, not dropped.
    assert len(report.valid_candles) == 2


def test_no_gap_detection_for_timeframe_without_known_interval() -> None:
    report = validate_candles([_candle(0), _candle(1000)], timeframe="MN")

    assert not any(issue.kind == "gap" for issue in report.issues)


def test_sorts_candles_by_timestamp_regardless_of_input_order() -> None:
    report = validate_candles([_candle(2), _candle(0), _candle(1)], timeframe="H1")

    assert [c.timestamp for c in report.valid_candles] == [
        _BASE_TIME,
        _BASE_TIME + timedelta(hours=1),
        _BASE_TIME + timedelta(hours=2),
    ]
