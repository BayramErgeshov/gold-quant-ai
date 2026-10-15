"""One-off initial model training script: fits and registers the first
classification/regression model pair for XAUUSD on real, backfilled
historical candles (see `scripts/mt5_historical_backfill.py`).

Run with the project's own virtual environment interpreter:

    ./.venv/Scripts/python.exe scripts/train_initial_models.py

POSTGRES_PASSWORD is read from the environment, never hardcoded. Only
writes to the `ml_models` registry table with status "training" —
promoting a version to "candidate"/"production" is a separate, explicit
decision per IMPLEMENTATION_ROADMAP.md ("No production strategy may
change automatically").
"""

from __future__ import annotations

import asyncio
import sys

from src.database.postgres.session import get_session
from src.engines.ml_engine.training import InsufficientTrainingDataError, TrainingService
from src.repositories.candle_repository import CandleRepository
from src.repositories.ml_model_repository import MLModelRepository
from src.repositories.symbol_repository import SymbolRepository

_TIMEFRAME_TRAINING_PARAMS: list[tuple[str, int, int]] = [
    # (timeframe, window_size, forward_bars)
    ("M15", 20, 8),
    ("H1", 20, 6),
    ("H4", 14, 4),
    ("D1", 14, 3),
]


async def main() -> int:
    async with get_session() as session:
        symbol = await SymbolRepository(session).get_by_name("XAUUSD")
        if symbol is None:
            print("FAILED: XAUUSD symbol not seeded. Run seed_primary_symbol first.")
            return 1

        service = TrainingService(
            candle_repository=CandleRepository(session),
            model_repository=MLModelRepository(session),
        )
        exit_code = 0
        for timeframe, window_size, forward_bars in _TIMEFRAME_TRAINING_PARAMS:
            model_name = f"xauusd_{timeframe.lower()}"
            try:
                result = await service.train(
                    symbol.id,
                    timeframe,
                    model_name=model_name,
                    window_size=window_size,
                    forward_bars=forward_bars,
                )
            except InsufficientTrainingDataError as exc:
                print(f"{timeframe}: SKIPPED - {exc}")
                exit_code = 1
                continue

            print(
                f"{timeframe}: classifier v{result.classification_record.version} "
                f"metrics={result.classification_record.metrics}"
            )
            print(
                f"{timeframe}: regressor  v{result.regression_record.version} "
                f"metrics={result.regression_record.metrics}"
            )

    return exit_code


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
