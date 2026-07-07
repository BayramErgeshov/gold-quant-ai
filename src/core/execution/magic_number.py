"""Deterministic magic number generation for the Execution Engine.

Per MT5_ENGINE.md "Magic Number": "Every strategy receives [a] Unique
Magic Number... Every order is linked to Strategy, Agent, Prediction,
Learning Record, Journal." A stable hash of the strategy name/version
keeps the same strategy's orders consistently tagged across restarts,
without requiring a manually maintained registry.
"""

from __future__ import annotations

import hashlib

_MAX_MAGIC_NUMBER = 2_147_483_647  # MT5 magic numbers are a 32-bit signed int


def compute_magic_number(strategy_name: str, strategy_version: str) -> int:
    """Compute a stable magic number for a strategy name/version pair.

    Args:
        strategy_name: Strategy identifier, e.g. "xauusd_h1_trend".
        strategy_version: Version tag, e.g. "1.0.0".

    Returns:
        A positive integer in [1, 2_147_483_647], stable across process
        restarts for the same `strategy_name`/`strategy_version`.
    """
    key = f"{strategy_name}:{strategy_version}".encode()
    digest = hashlib.sha256(key).hexdigest()
    return (int(digest, 16) % (_MAX_MAGIC_NUMBER - 1)) + 1
