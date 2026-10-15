"""Unit tests for the `CorrelatedInstrument` ORM model."""

from __future__ import annotations

import pytest

from src.models.correlated_instrument import CorrelatedInstrument

pytestmark = pytest.mark.unit


def test_repr_includes_name_and_category() -> None:
    instrument = CorrelatedInstrument(
        name="EURUSD", display_name="Euro vs US Dollar", mt5_symbol="EURUSD", category="fx"
    )

    assert repr(instrument) == "CorrelatedInstrument(name='EURUSD', category='fx')"
