"""Model training orchestration for the Machine Learning Engine.

Ties together the dataset builder, model wrappers, validation metrics and
model registry (MACHINE_LEARNING_ENGINE.md "Model Training": Training ->
Validation -> Out-of-Sample -> ... -> Production Candidate). New versions
are always registered with status "training"; promoting a version to
"candidate" or "production" is a separate, explicit decision — per
IMPLEMENTATION_ROADMAP.md "No production strategy may change
automatically. All proposed strategy updates must be presented for user
approval."
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sklearn.metrics import (
    accuracy_score,
    f1_score,
    mean_absolute_error,
    precision_score,
    r2_score,
    recall_score,
)

from src.common.logging import get_logger
from src.core.ml.features import FEATURE_NAMES
from src.core.ml.labels import LabelThresholds
from src.core.ml.model import ClassificationModel, RegressionModel
from src.engines.ml_engine.dataset import Sample, build_dataset, split_dataset
from src.models.ml_model import MLModel
from src.repositories.candle_repository import CandleRepository
from src.repositories.ml_model_repository import MLModelRepository

logger = get_logger(__name__)

_MIN_TRAINING_SAMPLES = 30
_MIN_SAMPLES_FOR_R2 = 2
_MAX_CANDLES_CONSIDERED = 1_000_000


class InsufficientTrainingDataError(RuntimeError):
    """Raised when there is not enough historical data to train a model."""


@dataclass(frozen=True, slots=True)
class TrainingResult:
    """Outcome of a single training run.

    Attributes:
        classification_model: The fitted classifier.
        regression_model: The fitted regressor.
        classification_record: The classifier's persisted registry entry.
        regression_record: The regressor's persisted registry entry.
    """

    classification_model: ClassificationModel
    regression_model: RegressionModel
    classification_record: MLModel
    regression_record: MLModel


def _predicted_labels(model: ClassificationModel, samples: list[Sample]) -> list[str]:
    predictions = []
    for sample in samples:
        probabilities = model.predict_proba(sample.features)
        predictions.append(max(probabilities, key=lambda label: probabilities[label]))
    return predictions


def _classification_metrics(
    model: ClassificationModel, samples: list[Sample]
) -> dict[str, float]:
    if not samples:
        return {}
    y_true = [sample.label for sample in samples]
    y_pred = _predicted_labels(model, samples)
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision": float(precision_score(y_true, y_pred, average="macro", zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, average="macro", zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
    }


def _regression_metrics(model: RegressionModel, samples: list[Sample]) -> dict[str, float]:
    if not samples:
        return {}
    y_true = [sample.forward_return_pct for sample in samples]
    y_pred = [model.predict(sample.features) for sample in samples]
    metrics = {"mae": float(mean_absolute_error(y_true, y_pred))}
    if len(samples) >= _MIN_SAMPLES_FOR_R2:
        metrics["r2"] = float(r2_score(y_true, y_pred))
    return metrics


class TrainingService:
    """Builds a dataset, fits models, validates them and registers new versions."""

    def __init__(
        self, *, candle_repository: CandleRepository, model_repository: MLModelRepository
    ) -> None:
        """Initialize the service (constructor injection).

        Args:
            candle_repository: Source of stored OHLCV candles for dataset building.
            model_repository: Persists newly trained model versions.
        """
        self._candles = candle_repository
        self._models = model_repository

    async def train(
        self,
        symbol_id: uuid.UUID,
        timeframe: str,
        *,
        model_name: str,
        window_size: int = 20,
        forward_bars: int = 10,
        thresholds: LabelThresholds | None = None,
    ) -> TrainingResult:
        """Train and register a classifier/regressor pair for one symbol/timeframe.

        Args:
            symbol_id: Symbol to train on.
            timeframe: One of `src.models.candle.TIMEFRAMES`.
            model_name: Base name for the registered models, e.g. "xauusd_h1".
                Registered as `f"{model_name}_classifier"`/`f"{model_name}_regressor"`.
            window_size: Number of candles used to compute each sample's features.
            forward_bars: Number of bars after each window to measure the outcome over.
            thresholds: Label decision boundaries; defaults to `LabelThresholds()`.

        Returns:
            A `TrainingResult` with the fitted models and their registry records.

        Raises:
            InsufficientTrainingDataError: If fewer than `_MIN_TRAINING_SAMPLES`
                samples can be built from stored candles — never trained on
                a fabricated or undersized dataset.
        """
        candles = await self._candles.list_range(
            symbol_id, timeframe, limit=_MAX_CANDLES_CONSIDERED
        )
        dataset = build_dataset(
            candles, window_size=window_size, forward_bars=forward_bars, thresholds=thresholds
        )
        if len(dataset.samples) < _MIN_TRAINING_SAMPLES:
            raise InsufficientTrainingDataError(
                f"Only {len(dataset.samples)} training samples available for "
                f"{model_name!r} (need at least {_MIN_TRAINING_SAMPLES}); "
                "collect more historical data before training."
            )

        split = split_dataset(dataset)

        classification_model = ClassificationModel(feature_names=FEATURE_NAMES)
        classification_model.fit(split.train)
        classification_metrics = _classification_metrics(classification_model, split.validation)

        regression_model = RegressionModel(feature_names=FEATURE_NAMES)
        regression_model.fit(split.train)
        regression_metrics = _regression_metrics(regression_model, split.validation)

        trained_at = datetime.now(UTC)
        classification_record = await self._register(
            name=f"{model_name}_classifier",
            model_type="classification",
            trained_at=trained_at,
            metrics=classification_metrics,
            n_samples=len(split.train),
        )
        regression_record = await self._register(
            name=f"{model_name}_regressor",
            model_type="regression",
            trained_at=trained_at,
            metrics=regression_metrics,
            n_samples=len(split.train),
        )

        logger.info(
            "ml_training_completed",
            symbol_id=str(symbol_id),
            timeframe=timeframe,
            model_name=model_name,
            train_samples=len(split.train),
            validation_samples=len(split.validation),
            test_samples=len(split.test),
        )
        return TrainingResult(
            classification_model=classification_model,
            regression_model=regression_model,
            classification_record=classification_record,
            regression_record=regression_record,
        )

    async def _register(
        self,
        *,
        name: str,
        model_type: str,
        trained_at: datetime,
        metrics: dict[str, float],
        n_samples: int,
    ) -> MLModel:
        version = await self._models.next_version(name)
        return await self._models.add(
            MLModel(
                name=name,
                version=version,
                model_type=model_type,
                status="training",
                trained_at=trained_at,
                feature_names=list(FEATURE_NAMES),
                hyperparameters={},
                metrics=metrics,
                n_samples=n_samples,
            )
        )
