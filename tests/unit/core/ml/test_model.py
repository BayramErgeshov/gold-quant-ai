"""Unit tests for classification/regression model wrappers."""

from __future__ import annotations

import pytest

from src.core.ml.model import ClassificationModel, RegressionModel
from src.engines.ml_engine.dataset import Sample

pytestmark = pytest.mark.unit

_FEATURE_NAMES = ("momentum_pct", "trend_slope_pct")


def _samples() -> list[Sample]:
    return [
        Sample(
            features={"momentum_pct": 5.0, "trend_slope_pct": 0.5},
            forward_return_pct=2.0,
            label="bullish",
        ),
        Sample(
            features={"momentum_pct": 4.5, "trend_slope_pct": 0.4},
            forward_return_pct=1.8,
            label="bullish",
        ),
        Sample(
            features={"momentum_pct": -5.0, "trend_slope_pct": -0.5},
            forward_return_pct=-2.0,
            label="bearish",
        ),
        Sample(
            features={"momentum_pct": -4.5, "trend_slope_pct": -0.4},
            forward_return_pct=-1.8,
            label="bearish",
        ),
    ]


def test_classification_model_raises_before_fit() -> None:
    model = ClassificationModel(feature_names=_FEATURE_NAMES)

    with pytest.raises(RuntimeError, match="must be fit"):
        model.predict_proba({"momentum_pct": 1.0, "trend_slope_pct": 1.0})


def test_classification_model_predicts_probabilities_summing_to_one() -> None:
    model = ClassificationModel(feature_names=_FEATURE_NAMES)
    model.fit(_samples())

    probabilities = model.predict_proba({"momentum_pct": 5.0, "trend_slope_pct": 0.5})

    assert set(probabilities) == {"bullish", "bearish"}
    assert probabilities["bullish"] == pytest.approx(1.0, abs=0.2)
    assert sum(probabilities.values()) == pytest.approx(1.0)


def test_classification_model_tracks_training_metadata() -> None:
    model = ClassificationModel(feature_names=_FEATURE_NAMES)
    model.fit(_samples())

    assert model.trained_at is not None
    assert model.n_samples == 4


def test_regression_model_raises_before_fit() -> None:
    model = RegressionModel(feature_names=_FEATURE_NAMES)

    with pytest.raises(RuntimeError, match="must be fit"):
        model.predict({"momentum_pct": 1.0, "trend_slope_pct": 1.0})


def test_regression_model_predicts_expected_move() -> None:
    model = RegressionModel(feature_names=_FEATURE_NAMES)
    model.fit(_samples())

    prediction = model.predict({"momentum_pct": 5.0, "trend_slope_pct": 0.5})

    assert prediction > 0


def test_regression_model_tracks_training_metadata() -> None:
    model = RegressionModel(feature_names=_FEATURE_NAMES)
    model.fit(_samples())

    assert model.trained_at is not None
    assert model.n_samples == 4
