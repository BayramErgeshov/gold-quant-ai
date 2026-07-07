"""Integration tests for `TrainingService`."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.engines.ml_engine.training import InsufficientTrainingDataError, TrainingService
from src.models.candle import Candle
from src.models.symbol import Symbol
from src.repositories.candle_repository import CandleRepository
from src.repositories.ml_model_repository import MLModelRepository
from src.repositories.symbol_repository import SymbolRepository

_BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


async def _make_symbol(session: AsyncSession) -> Symbol:
    return await SymbolRepository(session).add(Symbol(name="XAUUSD", display_name="Gold"))


def _make_candles(symbol_id: uuid.UUID, closes: list[float]) -> list[Candle]:
    return [
        Candle(
            symbol_id=symbol_id,
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


async def test_train_raises_when_insufficient_history(session: AsyncSession) -> None:
    symbol = await _make_symbol(session)
    candle_repo = CandleRepository(session)
    await candle_repo.insert_new(_make_candles(symbol.id, [100.0] * 10))
    service = TrainingService(
        candle_repository=candle_repo, model_repository=MLModelRepository(session)
    )

    with pytest.raises(InsufficientTrainingDataError):
        await service.train(symbol.id, "H1", model_name="xauusd_h1")


async def test_train_registers_classifier_and_regressor(session: AsyncSession) -> None:
    symbol = await _make_symbol(session)
    candle_repo = CandleRepository(session)
    closes = [100.0 + (index % 20) * 0.3 for index in range(200)]
    await candle_repo.insert_new(_make_candles(symbol.id, closes))
    model_repo = MLModelRepository(session)
    service = TrainingService(candle_repository=candle_repo, model_repository=model_repo)

    result = await service.train(
        symbol.id, "H1", model_name="xauusd_h1", window_size=10, forward_bars=5
    )

    assert result.classification_record.name == "xauusd_h1_classifier"
    assert result.classification_record.version == 1
    assert result.classification_record.status == "training"
    assert result.regression_record.name == "xauusd_h1_regressor"
    assert result.classification_model.trained_at is not None
    assert result.regression_model.trained_at is not None

    stored_classifier = await model_repo.get_latest("xauusd_h1_classifier")
    assert stored_classifier is not None
    assert stored_classifier.feature_names


async def test_train_increments_version_on_retrain(session: AsyncSession) -> None:
    symbol = await _make_symbol(session)
    candle_repo = CandleRepository(session)
    closes = [100.0 + (index % 20) * 0.3 for index in range(200)]
    await candle_repo.insert_new(_make_candles(symbol.id, closes))
    model_repo = MLModelRepository(session)
    service = TrainingService(candle_repository=candle_repo, model_repository=model_repo)

    await service.train(symbol.id, "H1", model_name="xauusd_h1", window_size=10, forward_bars=5)
    second_result = await service.train(
        symbol.id, "H1", model_name="xauusd_h1", window_size=10, forward_bars=5
    )

    assert second_result.classification_record.version == 2
