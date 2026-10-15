"""Classification and regression model wrappers for the Machine Learning Engine.

Per MACHINE_LEARNING_ENGINE.md "Model Types" and "Core Principles" ("No
black-box decisions... every prediction must be explainable"): both
wrappers use linear models (`LogisticRegression`, `LinearRegression`) so
every prediction can be decomposed into per-feature contributions
(`src.core.ml.explainability`). Tree/ensemble/sequence/transformer model
types from the same spec section are deferred until non-linear
relationships are demonstrated to matter more than explainability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sklearn.linear_model import LinearRegression, LogisticRegression

from src.engines.ml_engine.dataset import Sample


def to_feature_matrix(samples: list[Sample], feature_names: tuple[str, ...]) -> list[list[float]]:
    """Convert samples to a row-per-sample matrix in `feature_names` order.

    Shared with `src.core.ml.feature_importance` so both training and
    importance analysis build the exact same matrix layout.

    Args:
        samples: Samples to convert.
        feature_names: Feature vector key order.

    Returns:
        One row per sample, one column per feature name, in that order.
    """
    return [[sample.features[name] for name in feature_names] for sample in samples]


@dataclass(slots=True)
class ClassificationModel:
    """Wraps a multinomial logistic regression over the directional labels.

    Attributes:
        feature_names: Feature vector key order the model was trained on.
        trained_at: UTC timestamp of the last successful `fit`.
        n_samples: Number of training samples the model was fit on.
    """

    feature_names: tuple[str, ...]
    trained_at: datetime | None = None
    n_samples: int = 0
    _estimator: Any = field(default_factory=lambda: LogisticRegression(max_iter=1000), repr=False)

    def fit(self, samples: list[Sample]) -> None:
        """Fit the model on labeled samples.

        Args:
            samples: Training samples; should include at least two distinct labels.
        """
        x = to_feature_matrix(samples, self.feature_names)
        y = [sample.label for sample in samples]
        self._estimator.fit(x, y)
        self.trained_at = datetime.now(UTC)
        self.n_samples = len(samples)

    def predict_proba(self, features: dict[str, float]) -> dict[str, float]:
        """Predict class probabilities for a single feature vector.

        Args:
            features: A feature vector keyed by `self.feature_names`.

        Returns:
            Predicted probability per class label.

        Raises:
            RuntimeError: If called before `fit`.
        """
        if self.trained_at is None:
            raise RuntimeError("ClassificationModel must be fit before predicting")
        x = [[features[name] for name in self.feature_names]]
        probabilities = self._estimator.predict_proba(x)[0]
        return {
            str(label): float(probability)
            for label, probability in zip(self._estimator.classes_, probabilities, strict=True)
        }


@dataclass(slots=True)
class RegressionModel:
    """Wraps a linear regression predicting the expected forward return %.

    Attributes:
        feature_names: Feature vector key order the model was trained on.
        trained_at: UTC timestamp of the last successful `fit`.
        n_samples: Number of training samples the model was fit on.
    """

    feature_names: tuple[str, ...]
    trained_at: datetime | None = None
    n_samples: int = 0
    _estimator: Any = field(default_factory=LinearRegression, repr=False)

    def fit(self, samples: list[Sample]) -> None:
        """Fit the model on labeled samples.

        Args:
            samples: Training samples.
        """
        x = to_feature_matrix(samples, self.feature_names)
        y = [sample.forward_return_pct for sample in samples]
        self._estimator.fit(x, y)
        self.trained_at = datetime.now(UTC)
        self.n_samples = len(samples)

    def predict(self, features: dict[str, float]) -> float:
        """Predict the expected forward return % for a feature vector.

        Args:
            features: A feature vector keyed by `self.feature_names`.

        Returns:
            The predicted expected move, in percent.

        Raises:
            RuntimeError: If called before `fit`.
        """
        if self.trained_at is None:
            raise RuntimeError("RegressionModel must be fit before predicting")
        x = [[features[name] for name in self.feature_names]]
        return float(self._estimator.predict(x)[0])
