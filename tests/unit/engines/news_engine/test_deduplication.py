"""Unit tests for news content-hash deduplication."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.engines.news_engine.deduplication import compute_content_hash

pytestmark = pytest.mark.unit

_PUBLISHED_AT = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)


def test_hash_is_stable_for_identical_input() -> None:
    first = compute_content_hash(
        title="Fed holds rates steady", source="reuters.com", published_at=_PUBLISHED_AT
    )
    second = compute_content_hash(
        title="Fed holds rates steady", source="reuters.com", published_at=_PUBLISHED_AT
    )

    assert first == second


def test_hash_ignores_case_and_whitespace_differences() -> None:
    first = compute_content_hash(
        title="Fed Holds Rates Steady", source="Reuters.com", published_at=_PUBLISHED_AT
    )
    second = compute_content_hash(
        title="  fed   holds rates   steady  ", source="reuters.com", published_at=_PUBLISHED_AT
    )

    assert first == second


def test_hash_ignores_time_of_day_differences() -> None:
    later_same_day = _PUBLISHED_AT.replace(hour=23, minute=59)

    first = compute_content_hash(
        title="Fed holds rates steady", source="reuters.com", published_at=_PUBLISHED_AT
    )
    second = compute_content_hash(
        title="Fed holds rates steady", source="reuters.com", published_at=later_same_day
    )

    assert first == second


def test_hash_differs_for_different_titles() -> None:
    first = compute_content_hash(
        title="Fed holds rates steady", source="reuters.com", published_at=_PUBLISHED_AT
    )
    second = compute_content_hash(
        title="Fed cuts rates", source="reuters.com", published_at=_PUBLISHED_AT
    )

    assert first != second


def test_hash_differs_for_different_sources() -> None:
    first = compute_content_hash(
        title="Fed holds rates steady", source="reuters.com", published_at=_PUBLISHED_AT
    )
    second = compute_content_hash(
        title="Fed holds rates steady", source="bloomberg.com", published_at=_PUBLISHED_AT
    )

    assert first != second


def test_hash_differs_for_different_days() -> None:
    next_day = _PUBLISHED_AT.replace(day=2)

    first = compute_content_hash(
        title="Fed holds rates steady", source="reuters.com", published_at=_PUBLISHED_AT
    )
    second = compute_content_hash(
        title="Fed holds rates steady", source="reuters.com", published_at=next_day
    )

    assert first != second
