"""Unit tests for deterministic magic number generation."""

from __future__ import annotations

import pytest

from src.core.execution.magic_number import compute_magic_number

pytestmark = pytest.mark.unit


def test_is_stable_for_identical_input() -> None:
    first = compute_magic_number("xauusd_h1_trend", "1.0.0")
    second = compute_magic_number("xauusd_h1_trend", "1.0.0")

    assert first == second


def test_differs_for_different_strategy_names() -> None:
    first = compute_magic_number("xauusd_h1_trend", "1.0.0")
    second = compute_magic_number("xauusd_h4_trend", "1.0.0")

    assert first != second


def test_differs_for_different_versions() -> None:
    first = compute_magic_number("xauusd_h1_trend", "1.0.0")
    second = compute_magic_number("xauusd_h1_trend", "2.0.0")

    assert first != second


def test_is_a_positive_32_bit_integer() -> None:
    magic_number = compute_magic_number("xauusd_h1_trend", "1.0.0")

    assert 0 < magic_number <= 2_147_483_647
