"""Unit tests for `SignalWorkflow`'s pure-function helpers."""

from __future__ import annotations

import uuid

import pytest

from src.workflows.trade.pipeline import _MT5_COMMENT_MAX_LENGTH, _order_comment

pytestmark = pytest.mark.unit


def test_order_comment_stays_within_mt5s_length_limit() -> None:
    # A long strategy name + a full UUID would otherwise exceed MT5's
    # real, measured 31-character comment limit (retcode -2 'Invalid
    # "comment" argument').
    comment = _order_comment("a_fairly_long_strategy_name", uuid.uuid4())

    assert len(comment) <= _MT5_COMMENT_MAX_LENGTH


def test_order_comment_embeds_a_short_trade_id_prefix() -> None:
    trade_id = uuid.uuid4()

    comment = _order_comment("xauusd_m15_live", trade_id)

    assert str(trade_id)[:8] in comment
