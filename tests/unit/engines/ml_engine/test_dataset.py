"""Unit tests for the Machine Learning Engine's dataset builder."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from src.engines.ml_engine.dataset import build_dataset, split_dataset
from src.models.candle import Candle

pytestmark = pytest.mark.unit

_SYMBOL_ID = uuid.uuid4()
_BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


def _make_candles(closes: list[float]) -> list[Candle]:
    return [
        Candle(
            symbol_id=_SYMBOL_ID,
            timeframe="H1",
            timestamp=_BASE_TIME + timedelta(hours=index),
            open=close,
            high=close + 0.5,
            low=close - 0.5,
            close=close,
            source="test_fixture",
        )
        for index, close in enumerate(closes)
    ]


def test_returns_empty_dataset_when_insufficient_history() -> None:
    candles = _make_candles([100.0] * 10)

    dataset = build_dataset(candles, window_size=20, forward_bars=10)

    assert dataset.samples == []


def test_builds_expected_number_of_samples() -> None:
    candles = _make_candles([100.0 + index * 0.1 for index in range(50)])

    dataset = build_dataset(candles, window_size=20, forward_bars=10)

    # Valid end indices range over [window_size, len(candles) - forward_bars]: 21 samples.
    assert len(dataset.samples) == 21


def test_skips_samples_with_zero_entry_price() -> None:
    closes = [100.0, 101.0, 102.0, 103.0, 0.0, 105.0, 106.0, 107.0, 108.0, 109.0]
    candles = _make_candles(closes)

    dataset = build_dataset(candles, window_size=5, forward_bars=2)

    # end_index=5 uses entry_price=candles[4].close=0.0 and must be excluded;
    # end_index=6,7,8 remain valid, so 3 samples (not 4).
    assert len(dataset.samples) == 3


def test_sample_forward_return_matches_manual_calculation() -> None:
    closes = [100.0] * 20 + [110.0]
    candles = _make_candles(closes)

    dataset = build_dataset(candles, window_size=20, forward_bars=1)

    assert len(dataset.samples) == 1
    assert dataset.samples[0].forward_return_pct == pytest.approx(10.0)
    assert dataset.samples[0].label == "strong_bullish"


def test_split_dataset_is_chronological_and_non_overlapping() -> None:
    candles = _make_candles([100.0 + index * 0.1 for index in range(100)])
    dataset = build_dataset(candles, window_size=20, forward_bars=10)

    split = split_dataset(dataset, validation_fraction=0.2, test_fraction=0.2)

    assert len(split.train) + len(split.validation) + len(split.test) == len(dataset.samples)
    assert split.train == dataset.samples[: len(split.train)]
    assert split.test == dataset.samples[-len(split.test) :]


def test_split_dataset_handles_empty_dataset() -> None:
    from src.engines.ml_engine.dataset import Dataset

    split = split_dataset(Dataset(samples=[]))

    assert split.train == []
    assert split.validation == []
    assert split.test == []
