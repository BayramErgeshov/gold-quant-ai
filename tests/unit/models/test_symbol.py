"""Unit tests for the `Symbol` ORM model."""

from __future__ import annotations

import pytest

from src.models.symbol import Symbol

pytestmark = pytest.mark.unit


def test_repr_includes_name_and_primary_flag() -> None:
    symbol = Symbol(name="XAUUSD", display_name="Gold vs US Dollar", is_primary=True)

    assert repr(symbol) == "Symbol(name='XAUUSD', is_primary=True)"
