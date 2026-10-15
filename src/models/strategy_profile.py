"""ORM models for Strategy Builder (DATABASE.md: `strategy_profiles`,
`strategy_profile_modules`).

Per the "Complete Strategy Builder" production requirement: "Enable/
disable every analysis module independently... For each enabled module:
configure Weight, Minimum confidence, Enable/Disable. Allow saving/
loading profiles." A profile that does not list a given module leaves
that module at its current default behavior (enabled, weight 1.0, no
minimum confidence) -- profiles only ever override what they explicitly
list, per this platform's existing "None means use the current default"
convention (`src.models.runtime_settings.RuntimeSettings`).
"""

from __future__ import annotations

import uuid

from sqlalchemy import Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.postgres.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class StrategyProfile(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A named, reusable module configuration (e.g. "Conservative", "News Trading").

    Attributes:
        name: Unique, user-chosen profile name.
        modules: This profile's own per-module overrides.
    """

    __tablename__ = "strategy_profiles"

    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)

    modules: Mapped[list[StrategyProfileModule]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"StrategyProfile(name={self.name!r})"


class StrategyProfileModule(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One module's override within a `StrategyProfile`.

    Attributes:
        profile_id: Owning `StrategyProfile`.
        module_name: One of `src.engines.chief_ai.strategy_profile.MODULE_NAMES`.
        enabled: Whether this module contributes to the decision at all.
        weight: Relative weight applied to this module's vote when enabled.
        min_confidence: Minimum confidence (0.0-1.0) this module's own
            report must clear to be counted this cycle. None means no
            module-specific floor beyond the strategy's own overall
            confidence threshold.
    """

    __tablename__ = "strategy_profile_modules"
    __table_args__ = (
        UniqueConstraint("profile_id", "module_name", name="uq_strategy_profile_modules_module"),
    )

    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("strategy_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    module_name: Mapped[str] = mapped_column(String(50), nullable=False)
    enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    weight: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    min_confidence: Mapped[float | None] = mapped_column(Float)

    profile: Mapped[StrategyProfile] = relationship(back_populates="modules")

    def __repr__(self) -> str:
        return f"StrategyProfileModule(module_name={self.module_name!r}, enabled={self.enabled})"
