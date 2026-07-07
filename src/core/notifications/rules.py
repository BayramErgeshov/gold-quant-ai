"""Notification dispatch rules for the Telegram integration.

Per TELEGRAM.md "Message Rules" / "Notification Priority": "Never spam.
Never repeat identical information... Critical messages bypass silent
mode." Anti-spam dedup and priority handling, kept independent of any
specific message type.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal

Priority = Literal["critical", "high", "medium", "low", "silent"]


def compute_message_hash(text: str) -> str:
    """Compute a stable dedup hash for a message body.

    Args:
        text: The formatted message text.

    Returns:
        A 64-character hex SHA-256 digest.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class NotificationDecision:
    """Whether a notification should actually be sent this time."""

    should_send: bool
    reason: str


def should_send_notification(
    *, message_hash: str, last_sent_hash: str | None, priority: Priority
) -> NotificationDecision:
    """Decide whether to send a notification, per TELEGRAM.md "Message Rules".

    Args:
        message_hash: Hash of the message about to be sent
            (`compute_message_hash`).
        last_sent_hash: Hash of the last message sent on this channel, if any.
        priority: The message's priority. "critical" always bypasses dedup
            (TELEGRAM.md: "Critical messages bypass silent mode").

    Returns:
        A `NotificationDecision`.
    """
    if priority == "critical":
        return NotificationDecision(should_send=True, reason="critical_bypasses_dedup")
    if message_hash == last_sent_hash:
        return NotificationDecision(should_send=False, reason="duplicate_of_last_message")
    return NotificationDecision(should_send=True, reason="new_content")
