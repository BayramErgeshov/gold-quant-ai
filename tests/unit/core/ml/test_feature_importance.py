"""Unit tests for permutation feature importance."""

from __future__ import annotations

import random

import pytest

from src.core.ml.feature_importance import (
    compute_classification_feature_importance,
    compute_regression_feature_importance,
)
from src.core.ml.model import ClassificationModel, RegressionModel
from src.engines.ml_engine.dataset import Sample

pytestmark = pytest.mark.unit

_FEATURE_NAMES = ("informative", "noise")


def _samples(n: int = 60) -> list[Sample]:
    rng = random.Random(42)
    samples = []
    for _ in range(n):
        informative = rng.uniform(-5.0, 5.0)
        noise = rng.uniform(-5.0, 5.0)
        forward_return_pct = informative * 0.4
        label = "bullish" if informative > 0 else "bearish"
        samples.append(
            Sample(
                features={"informative": informative, "noise": noise},
                forward_return_pct=forward_return_pct,
                label=label,
            )
        )
    return samples


def test_classification_importance_raises_before_fit() -> None:
    model = ClassificationModel(feature_names=_FEATURE_NAMES)

    with pytest.raises(RuntimeError, match="must be fit"):
        compute_classification_feature_importance(model, _samples())


def test_classification_importance_ranks_informative_feature_first() -> None:
    model = ClassificationModel(feature_names=_FEATURE_NAMES)
    samples = _samples()
    model.fit(samples)

    ranked = compute_classification_feature_importance(model, samples, n_repeats=5)

    assert ranked[0].feature_name == "informative"


def test_regression_importance_raises_before_fit() -> None:
    model = RegressionModel(feature_names=_FEATURE_NAMES)

    with pytest.raises(RuntimeError, match="must be fit"):
        compute_regression_feature_importance(model, _samples())


def test_regression_importance_ranks_informative_feature_first() -> None:
    model = RegressionModel(feature_names=_FEATURE_NAMES)
    samples = _samples()
    model.fit(samples)

    ranked = compute_regression_feature_importance(model, samples, n_repeats=5)

    assert ranked[0].feature_name == "informative"
