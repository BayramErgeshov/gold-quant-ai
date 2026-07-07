"""Unit tests for the `BookClaim` ORM model."""

from __future__ import annotations

import uuid

import pytest

from src.models.book_claim import BookClaim

pytestmark = pytest.mark.unit


def test_repr_includes_topic_and_status() -> None:
    # `validation_status` has a server/ORM-flush-time default of "pending";
    # it is not yet populated on a plain in-memory (unflushed) instance, so
    # it is passed explicitly here to test `__repr__` in isolation.
    claim = BookClaim(
        book_id=uuid.uuid4(),
        chunk_id=uuid.uuid4(),
        statement="Order blocks increase reversal probability.",
        topic="smart_money",
        validation_status="pending",
    )

    assert repr(claim) == "BookClaim(topic='smart_money', status='pending')"
