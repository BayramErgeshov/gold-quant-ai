"""Unit tests for the MT5 execution gateway abstraction.

`MetaTrader5` is not installed in this environment (it requires a running
Windows terminal and broker credentials), so `RealMT5Client`'s logic is
exercised against a fake module injected into `sys.modules` — the same
technique used elsewhere in this codebase for `httpx.AsyncClient`.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.core.execution.mt5_client import MT5Client, OrderRequest, RealMT5Client
from src.settings import get_settings

pytestmark = pytest.mark.unit

_ORDER_TYPE_BUY = 0
_ORDER_TYPE_SELL = 1
_TRADE_RETCODE_DONE = 10009


class _FakeMT5:
    ORDER_TYPE_BUY = _ORDER_TYPE_BUY
    ORDER_TYPE_SELL = _ORDER_TYPE_SELL
    ORDER_TYPE_BUY_LIMIT = 2
    ORDER_TYPE_SELL_LIMIT = 3
    ORDER_TYPE_BUY_STOP = 4
    ORDER_TYPE_SELL_STOP = 5
    ORDER_TYPE_BUY_STOP_LIMIT = 6
    ORDER_TYPE_SELL_STOP_LIMIT = 7
    TRADE_ACTION_DEAL = 1
    TRADE_ACTION_PENDING = 5
    TRADE_ACTION_SLTP = 6
    TRADE_ACTION_REMOVE = 8
    TRADE_RETCODE_DONE = _TRADE_RETCODE_DONE
    ACCOUNT_TRADE_MODE_DEMO = 0

    def __init__(self) -> None:
        self.initialize_result = True
        self.account_info_result: object | None = SimpleNamespace(
            login=12345,
            company="Test Broker",
            server="Test-Server",
            balance=10_000.0,
            equity=10_050.0,
            margin=100.0,
            margin_free=9_950.0,
            margin_level=99.5,
            currency="USD",
            leverage=100,
            trade_mode=self.ACCOUNT_TRADE_MODE_DEMO,
            trade_allowed=True,
        )
        self.order_send_result: object | None = SimpleNamespace(
            retcode=_TRADE_RETCODE_DONE, order=555, price=2000.0, comment="done"
        )
        self.positions_get_result: tuple[object, ...] = (
            SimpleNamespace(ticket=555, symbol="XAUUSD", volume=1.0, type=_ORDER_TYPE_BUY),
        )
        self.last_error_result = (1, "no error")
        self.last_request: dict[str, object] | None = None

    def initialize(self, **kwargs: object) -> bool:
        return self.initialize_result

    def account_info(self) -> object | None:
        return self.account_info_result

    def order_send(self, request: dict[str, object]) -> object | None:
        self.last_request = request
        return self.order_send_result

    def positions_get(self, ticket: int) -> tuple[object, ...]:
        return self.positions_get_result

    def last_error(self) -> tuple[int, str]:
        return self.last_error_result


@pytest.fixture
def fake_mt5() -> _FakeMT5:
    fake = _FakeMT5()
    with patch.dict(sys.modules, {"MetaTrader5": fake}):
        yield fake


def test_mt5_client_cannot_be_instantiated_directly() -> None:
    with pytest.raises(TypeError):
        MT5Client()  # type: ignore[abstract]


async def test_connect_succeeds(fake_mt5: _FakeMT5) -> None:
    client = RealMT5Client(get_settings())

    connected = await client.connect()

    assert connected is True
    assert await client.is_connected() is True


async def test_connect_fails_when_initialize_returns_false(fake_mt5: _FakeMT5) -> None:
    fake_mt5.initialize_result = False
    client = RealMT5Client(get_settings())

    connected = await client.connect()

    assert connected is False


async def test_get_account_info_maps_fields(fake_mt5: _FakeMT5) -> None:
    client = RealMT5Client(get_settings())

    info = await client.get_account_info()

    assert info.login == 12345
    assert info.broker == "Test Broker"
    assert info.is_demo is True
    assert info.trading_allowed is True


async def test_get_account_info_raises_when_none(fake_mt5: _FakeMT5) -> None:
    fake_mt5.account_info_result = None
    client = RealMT5Client(get_settings())

    with pytest.raises(ConnectionError):
        await client.get_account_info()


async def test_place_market_order_sends_deal_action(fake_mt5: _FakeMT5) -> None:
    client = RealMT5Client(get_settings())
    request = OrderRequest(
        symbol="XAUUSD",
        order_type="buy",
        volume=1.0,
        stop_loss=1990.0,
        take_profit=2010.0,
        magic_number=42,
    )

    result = await client.place_order(request)

    assert result.success is True
    assert result.broker_ticket == "555"
    assert fake_mt5.last_request is not None
    assert fake_mt5.last_request["action"] == fake_mt5.TRADE_ACTION_DEAL
    assert fake_mt5.last_request["tp"] == 2010.0


async def test_place_pending_order_sends_pending_action_with_price(fake_mt5: _FakeMT5) -> None:
    client = RealMT5Client(get_settings())
    request = OrderRequest(
        symbol="XAUUSD",
        order_type="buy_limit",
        volume=1.0,
        stop_loss=1990.0,
        take_profit=None,
        magic_number=42,
        price=1995.0,
    )

    await client.place_order(request)

    assert fake_mt5.last_request is not None
    assert fake_mt5.last_request["action"] == fake_mt5.TRADE_ACTION_PENDING
    assert fake_mt5.last_request["price"] == 1995.0
    assert "tp" not in fake_mt5.last_request


async def test_place_order_reports_failure_on_bad_retcode(fake_mt5: _FakeMT5) -> None:
    fake_mt5.order_send_result = SimpleNamespace(
        retcode=99999, order=0, price=None, comment="rejected"
    )
    client = RealMT5Client(get_settings())
    request = OrderRequest(
        symbol="XAUUSD",
        order_type="sell",
        volume=1.0,
        stop_loss=2010.0,
        take_profit=None,
        magic_number=42,
    )

    result = await client.place_order(request)

    assert result.success is False
    assert result.broker_ticket is None
    assert result.error_message is not None
    assert "99999" in result.error_message


async def test_place_order_handles_none_response(fake_mt5: _FakeMT5) -> None:
    fake_mt5.order_send_result = None
    client = RealMT5Client(get_settings())
    request = OrderRequest(
        symbol="XAUUSD",
        order_type="buy",
        volume=1.0,
        stop_loss=1990.0,
        take_profit=None,
        magic_number=42,
    )

    result = await client.place_order(request)

    assert result.success is False
    assert result.error_message is not None


async def test_modify_order_sends_sltp_action(fake_mt5: _FakeMT5) -> None:
    client = RealMT5Client(get_settings())

    result = await client.modify_order("555", stop_loss=1995.0, take_profit=2020.0)

    assert result.success is True
    assert fake_mt5.last_request is not None
    assert fake_mt5.last_request["action"] == fake_mt5.TRADE_ACTION_SLTP
    assert fake_mt5.last_request["position"] == 555
    assert fake_mt5.last_request["sl"] == 1995.0
    assert fake_mt5.last_request["tp"] == 2020.0


async def test_close_position_sends_opposite_direction_deal(fake_mt5: _FakeMT5) -> None:
    client = RealMT5Client(get_settings())

    result = await client.close_position("555")

    assert result.success is True
    assert fake_mt5.last_request is not None
    assert fake_mt5.last_request["type"] == fake_mt5.ORDER_TYPE_SELL
    assert fake_mt5.last_request["volume"] == 1.0


async def test_close_position_partial_volume(fake_mt5: _FakeMT5) -> None:
    client = RealMT5Client(get_settings())

    await client.close_position("555", volume=0.5)

    assert fake_mt5.last_request is not None
    assert fake_mt5.last_request["volume"] == 0.5


async def test_close_position_returns_failure_when_not_found(fake_mt5: _FakeMT5) -> None:
    fake_mt5.positions_get_result = ()
    client = RealMT5Client(get_settings())

    result = await client.close_position("999")

    assert result.success is False
    assert result.error_message is not None
    assert "999" in result.error_message


async def test_cancel_order_sends_remove_action(fake_mt5: _FakeMT5) -> None:
    client = RealMT5Client(get_settings())

    result = await client.cancel_order("555")

    assert result.success is True
    assert fake_mt5.last_request is not None
    assert fake_mt5.last_request["action"] == fake_mt5.TRADE_ACTION_REMOVE
    assert fake_mt5.last_request["order"] == 555
