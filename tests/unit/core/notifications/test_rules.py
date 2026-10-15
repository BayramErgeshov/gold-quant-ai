"""Unit tests for notification dispatch rules."""

from __future__ import annotations

import pytest

from src.core.notifications.rules import compute_message_hash, should_send_notification

pytestmark = pytest.mark.unit


def test_message_hash_is_stable() -> None:
    assert compute_message_hash("hello") == compute_message_hash("hello")


def test_message_hash_differs_for_different_text() -> None:
    assert compute_message_hash("hello") != compute_message_hash("world")


def test_sends_new_content() -> None:
    decision = should_send_notification(message_hash="abc", last_sent_hash="xyz", priority="medium")

    assert decision.should_send is True
    assert decision.reason == "new_content"


def test_sends_first_message_with_no_prior_hash() -> None:
    decision = should_send_notification(message_hash="abc", last_sent_hash=None, priority="low")

    assert decision.should_send is True


def test_suppresses_duplicate_message() -> None:
    decision = should_send_notification(message_hash="abc", last_sent_hash="abc", priority="medium")

    assert decision.should_send is False
    assert decision.reason == "duplicate_of_last_message"


def test_critical_bypasses_dedup() -> None:
    decision = should_send_notification(
        message_hash="abc", last_sent_hash="abc", priority="critical"
    )

    assert decision.should_send is True
    assert decision.reason == "critical_bypasses_dedup"
