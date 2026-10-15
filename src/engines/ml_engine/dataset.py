"""Dataset construction for the Machine Learning Engine.

Per MACHINE_LEARNING_ENGINE.md "Dataset Builder": assembles labeled
training samples from stored candles. Each sample's features are computed
strictly from candles *before* its forward-return outcome window, so no
sample ever sees its own future — consistent with the "Training ->
Validation -> Out-of-Sample -> Walk Forward" ordering in "Model Training".
"""

from __future__ import annotations

from dataclasses import dataclass

from src.core.ml.features import build_feature_vector
from src.core.ml.labels import LabelThresholds, compute_label
from src.models.candle import Candle
from src.utils.statistics import forward_return_pct


@dataclass(frozen=True, slots=True)
class Sample:
    """A single labeled training sample.

    Attributes:
        features: Feature vector for the window ending at this sample's timestamp.
        forward_return_pct: Realized forward return used to derive `label`.
        label: Directional classification label (`src.core.ml.labels.LABELS`).
    """

    features: dict[str, float]
    forward_return_pct: float
    label: str


@dataclass(frozen=True, slots=True)
class Dataset:
    """A chronologically ordered set of labeled samples."""

    samples: list[Sample]


def build_dataset(
    candles: list[Candle],
    *,
    window_size: int = 20,
    forward_bars: int = 10,
    thresholds: LabelThresholds | None = None,
) -> Dataset:
    """Build labeled samples from a chronologically ordered candle series.

    Args:
        candles: Candles ordered by timestamp ascending.
        window_size: Number of candles used to compute each sample's features.
        forward_bars: Number of bars after each window to measure the
            outcome return over.
        thresholds: Label decision boundaries; defaults to `LabelThresholds()`.

    Returns:
        Samples ordered chronologically by window end. Empty if there is
        not enough history for even one full window plus its forward-return
        outcome — never a fabricated sample.
    """
    samples: list[Sample] = []
    for end_index in range(window_size, len(candles) - forward_bars + 1):
        window = candles[end_index - window_size : end_index]
        entry_price = candles[end_index - 1].close
        exit_price = candles[end_index - 1 + forward_bars].close
        if entry_price == 0:
            continue

        return_pct = forward_return_pct(entry_price, exit_price)
        samples.append(
            Sample(
                features=build_feature_vector(window),
                forward_return_pct=return_pct,
                label=compute_label(return_pct, thresholds),
            )
        )
    return Dataset(samples=samples)


@dataclass(frozen=True, slots=True)
class DatasetSplit:
    """Chronologically ordered train/validation/test partitions.

    Per MACHINE_LEARNING_ENGINE.md's training pipeline ("Training ->
    Validation -> Out-of-Sample"): splits are taken in time order, never
    shuffled, so validation/test always evaluate the model on strictly
    later data than it was trained on.
    """

    train: list[Sample]
    validation: list[Sample]
    test: list[Sample]


def split_dataset(
    dataset: Dataset, *, validation_fraction: float = 0.15, test_fraction: float = 0.15
) -> DatasetSplit:
    """Split a dataset into chronologically ordered train/validation/test sets.

    Args:
        dataset: Samples ordered chronologically.
        validation_fraction: Fraction of samples reserved for validation.
        test_fraction: Fraction of samples reserved for the out-of-sample test set.

    Returns:
        A `DatasetSplit` with no shuffling — the earliest samples go to
        `train`, the middle to `validation`, and the most recent to `test`.
    """
    total = len(dataset.samples)
    test_size = int(total * test_fraction)
    validation_size = int(total * validation_fraction)
    train_end = total - validation_size - test_size

    return DatasetSplit(
        train=dataset.samples[:train_end],
        validation=dataset.samples[train_end : train_end + validation_size],
        test=dataset.samples[train_end + validation_size :],
    )
