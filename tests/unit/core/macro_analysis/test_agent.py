"""Unit tests for `src.core.macro_analysis.agent`."""

from __future__ import annotations

from datetime import date

import pytest

from src.core.macro_analysis.agent import MacroAgent, MacroObservation

pytestmark = pytest.mark.unit


def test_macro_observation_holds_date_and_value() -> None:
    observation = MacroObservation(observed_on=date(2026, 1, 1), value=3.5)

    assert observation.observed_on == date(2026, 1, 1)
    assert observation.value == 3.5


def test_macro_agent_cannot_be_instantiated_directly() -> None:
    with pytest.raises(TypeError):
        MacroAgent()  # type: ignore[abstract]
