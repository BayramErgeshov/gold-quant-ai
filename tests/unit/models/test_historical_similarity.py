"""Unit tests for the `HistoricalSimilarity` ORM model."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from src.models.historical_similarity import HistoricalSimilarity

pytestmark = pytest.mark.unit


def test_repr_includes_query_matched_and_score() -> None:
    query_ts = datetime(2026, 1, 1, tzinfo=UTC)
    matched_ts = datetime(2020, 5, 1, tzinfo=UTC)
    similarity = HistoricalSimilarity(
        symbol_id=uuid.uuid4(),
        timeframe="D1",
        query_timestamp=query_ts,
        matched_timestamp=matched_ts,
        similarity_score=0.876,
    )

    assert repr(similarity) == (
        f"HistoricalSimilarity(query={query_ts!r}, matched={matched_ts!r}, score=0.876)"
    )
