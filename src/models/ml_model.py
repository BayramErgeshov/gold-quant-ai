"""ORM model for the ML Model Registry (DATABASE.md: `ml_models`).

Per MACHINE_LEARNING_ENGINE.md "Model Versioning": "Every model stores
Version, Training Date, Features, Parameters, Validation, Performance,
Approval, Rollback." One row is one trained, versioned snapshot of a named
model; `status` tracks its place in the "Production Candidate" lifecycle
("Model Training": Training -> ... -> Production Candidate).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, CheckConstraint, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.database.postgres.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

MODEL_TYPES: tuple[str, ...] = ("classification", "regression")
MODEL_STATUSES: tuple[str, ...] = ("training", "candidate", "production", "retired")


class MLModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A single trained, versioned model snapshot.

    Attributes:
        name: Model family name, e.g. "xauusd_direction_classifier".
        version: Monotonically increasing version number within `name`.
        model_type: One of `MODEL_TYPES`.
        status: One of `MODEL_STATUSES` (MACHINE_LEARNING_ENGINE.md
            "Model Comparison": Current Production / Experimental /
            Candidate / Historical Best).
        trained_at: When training completed (UTC).
        feature_names: Ordered feature vector keys the model expects.
        hyperparameters: Estimator hyperparameters used for training.
        metrics: Validation/performance metrics (e.g. accuracy, Brier score).
        n_samples: Number of training samples the model was fit on.
    """

    __tablename__ = "ml_models"
    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_ml_models_name_version"),
        CheckConstraint(f"model_type IN {MODEL_TYPES}", name="ck_ml_models_model_type_valid"),
        CheckConstraint(f"status IN {MODEL_STATUSES}", name="ck_ml_models_status_valid"),
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    model_type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="training", nullable=False, index=True)
    trained_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    feature_names: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    hyperparameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    n_samples: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    def __repr__(self) -> str:
        return f"MLModel(name={self.name!r}, version={self.version!r}, status={self.status!r})"
