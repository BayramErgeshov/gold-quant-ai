"""MT5 execution gateway abstraction.

Per MT5_ENGINE.md: "The MT5 Engine is responsible for all communication
between GOLD QUANT AI and MetaTrader 5... It never generates trading
ideas. It only executes approved decisions." `MT5Client` is the gateway
interface every caller depends on; `RealMT5Client` wraps the official
`MetaTrader5` Python package.

`RealMT5Client` requires a running MT5 terminal (Windows only) and valid
broker credentials (`MT5_LOGIN`/`MT5_PASSWORD`/`MT5_SERVER` in `.env` —
see `src.core.config.env_settings.MT5EnvSettings`) — it activates
automatically once those are set, mirroring the Data Collection Engine's
provider-activation pattern (DATA_COLLECTION_ENGINE.md). No live MT5
terminal or broker account was available while writing this client, so
its `MetaTrader5.order_send()` request construction, while built strictly
from the package's documented API, has not been exercised against a real
broker; MT5_ENGINE.md's "Initial Mode: Demo Mode" rule means it must be
validated against a demo account before any live use. The `MetaTrader5`
package is imported lazily so this module — and the interface/dataclasses
below — remain importable and testable without the package installed.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Literal

from src.settings import Settings, get_settings

OrderType = Literal[
    "buy",
    "sell",
    "buy_limit",
    "sell_limit",
    "buy_stop",
    "sell_stop",
    "buy_stop_limit",
    "sell_stop_limit",
]

_MARKET_ORDER_TYPES: frozenset[OrderType] = frozenset({"buy", "sell"})


@dataclass(frozen=True, slots=True)
class AccountInfo:
    """Live MT5 account state (MT5_ENGINE.md "Account Information")."""

    login: int
    broker: str
    server: str
    balance: float
    equity: float
    margin: float
    free_margin: float
    margin_level: float
    currency: str
    leverage: int
    is_demo: bool
    trading_allowed: bool


@dataclass(frozen=True, slots=True)
class OrderRequest:
    """Everything needed to place one order (MT5_ENGINE.md "Order Parameters").

    Attributes:
        symbol: Broker symbol name, e.g. "XAUUSD".
        order_type: One of `OrderType`.
        volume: Order size, in the broker's lot convention.
        stop_loss: Protective stop price. Every order requires one
            (RISK_ENGINE.md "Every trade must have a predefined invalidation level").
        take_profit: Target price, if set.
        magic_number: Strategy identifier (MT5_ENGINE.md "Magic Number").
        comment: Broker-visible order comment.
        price: Limit/stop price; ignored for market orders ("buy"/"sell").
    """

    symbol: str
    order_type: OrderType
    volume: float
    stop_loss: float
    take_profit: float | None
    magic_number: int
    comment: str = ""
    price: float | None = None


@dataclass(frozen=True, slots=True)
class OrderResult:
    """The gateway's response to placing/modifying/closing/cancelling an order."""

    success: bool
    broker_ticket: str | None
    filled_price: float | None
    error_message: str | None = None


class MT5Client(ABC):
    """Execution gateway interface (MT5_ENGINE.md "Primary Responsibilities")."""

    @abstractmethod
    async def connect(self) -> bool:
        """Connect and authenticate to the MT5 terminal.

        Returns:
            True if the connection and authentication succeeded.
        """

    @abstractmethod
    async def is_connected(self) -> bool:
        """Check whether the terminal connection is currently alive."""

    @abstractmethod
    async def get_account_info(self) -> AccountInfo:
        """Fetch current account balance/equity/margin/permissions."""

    @abstractmethod
    async def place_order(self, request: OrderRequest) -> OrderResult:
        """Submit a new order to the broker."""

    @abstractmethod
    async def modify_order(
        self,
        broker_ticket: str,
        *,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> OrderResult:
        """Modify an existing order/position's stop loss and/or take profit.

        MT5_ENGINE.md "Order Modification" forbids widening the stop or
        removing it entirely — enforcing that rule is the caller's
        responsibility (`src.core.execution.order_validation`), not this
        interface's.
        """

    @abstractmethod
    async def close_position(
        self, broker_ticket: str, *, volume: float | None = None
    ) -> OrderResult:
        """Close a position, fully or partially.

        Args:
            broker_ticket: The position to close.
            volume: Volume to close; None closes the full position.
        """

    @abstractmethod
    async def cancel_order(self, broker_ticket: str) -> OrderResult:
        """Cancel a pending (not-yet-filled) order."""


class RealMT5Client(MT5Client):
    """Wraps the official `MetaTrader5` Python package. See module docstring."""

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialize the client.

        Args:
            settings: Application settings. Defaults to `get_settings()`.
        """
        self._settings = settings or get_settings()
        self._connected = False

    async def connect(self) -> bool:
        """Connect and authenticate using `MT5EnvSettings`.

        Returns:
            True if `MetaTrader5.initialize()` succeeded.
        """
        import MetaTrader5 as mt5  # noqa: N813 - matches the package's own casing

        credentials = self._settings.mt5_env
        initialized = mt5.initialize(
            path=credentials.terminal_path or None,
            login=int(credentials.login) if credentials.login else None,
            password=credentials.password.get_secret_value() or None,
            server=credentials.server or None,
        )
        self._connected = bool(initialized)
        return self._connected

    async def is_connected(self) -> bool:
        """Return the last-known connection state from `connect()`."""
        return self._connected

    async def get_account_info(self) -> AccountInfo:
        """Fetch account state via `MetaTrader5.account_info()`.

        Returns:
            The current `AccountInfo`.

        Raises:
            ConnectionError: If the terminal returned no account info
                (not connected/authenticated).
        """
        import MetaTrader5 as mt5  # noqa: N813

        info = mt5.account_info()
        if info is None:
            raise ConnectionError("MetaTrader5.account_info() returned None; not connected")
        return AccountInfo(
            login=info.login,
            broker=info.company,
            server=info.server,
            balance=info.balance,
            equity=info.equity,
            margin=info.margin,
            free_margin=info.margin_free,
            margin_level=info.margin_level,
            currency=info.currency,
            leverage=info.leverage,
            is_demo=info.trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO,
            trading_allowed=bool(info.trade_allowed),
        )

    async def place_order(self, request: OrderRequest) -> OrderResult:
        """Submit an order via `MetaTrader5.order_send()`.

        Args:
            request: The order to place.

        Returns:
            An `OrderResult` reflecting the broker's response.
        """
        import MetaTrader5 as mt5  # noqa: N813

        order_type_map = {
            "buy": mt5.ORDER_TYPE_BUY,
            "sell": mt5.ORDER_TYPE_SELL,
            "buy_limit": mt5.ORDER_TYPE_BUY_LIMIT,
            "sell_limit": mt5.ORDER_TYPE_SELL_LIMIT,
            "buy_stop": mt5.ORDER_TYPE_BUY_STOP,
            "sell_stop": mt5.ORDER_TYPE_SELL_STOP,
            "buy_stop_limit": mt5.ORDER_TYPE_BUY_STOP_LIMIT,
            "sell_stop_limit": mt5.ORDER_TYPE_SELL_STOP_LIMIT,
        }
        is_market_order = request.order_type in _MARKET_ORDER_TYPES
        mt5_request: dict[str, object] = {
            "action": mt5.TRADE_ACTION_DEAL if is_market_order else mt5.TRADE_ACTION_PENDING,
            "symbol": request.symbol,
            "volume": request.volume,
            "type": order_type_map[request.order_type],
            "sl": request.stop_loss,
            "magic": request.magic_number,
            "comment": request.comment,
        }
        if request.take_profit is not None:
            mt5_request["tp"] = request.take_profit
        if not is_market_order and request.price is not None:
            mt5_request["price"] = request.price

        result = mt5.order_send(mt5_request)
        return self._to_order_result(result)

    async def modify_order(
        self,
        broker_ticket: str,
        *,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> OrderResult:
        """Modify a position's stop/target via `TRADE_ACTION_SLTP`.

        Args:
            broker_ticket: The position ticket to modify.
            stop_loss: New protective stop, if changing it.
            take_profit: New target price, if changing it.

        Returns:
            An `OrderResult` reflecting the broker's response.
        """
        import MetaTrader5 as mt5  # noqa: N813

        mt5_request: dict[str, object] = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": int(broker_ticket),
        }
        if stop_loss is not None:
            mt5_request["sl"] = stop_loss
        if take_profit is not None:
            mt5_request["tp"] = take_profit

        result = mt5.order_send(mt5_request)
        return self._to_order_result(result)

    async def close_position(
        self, broker_ticket: str, *, volume: float | None = None
    ) -> OrderResult:
        """Close a position via an opposite-direction `TRADE_ACTION_DEAL`.

        Args:
            broker_ticket: The position ticket to close.
            volume: Volume to close; None closes the full position volume.

        Returns:
            An `OrderResult` reflecting the broker's response.
        """
        import MetaTrader5 as mt5  # noqa: N813

        positions = mt5.positions_get(ticket=int(broker_ticket))
        if not positions:
            return OrderResult(
                success=False,
                broker_ticket=broker_ticket,
                filled_price=None,
                error_message=f"No open position found for ticket {broker_ticket!r}",
            )

        position = positions[0]
        close_type = (
            mt5.ORDER_TYPE_SELL if position.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        )
        mt5_request: dict[str, object] = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": position.symbol,
            "volume": volume if volume is not None else position.volume,
            "type": close_type,
            "position": position.ticket,
        }
        result = mt5.order_send(mt5_request)
        return self._to_order_result(result)

    async def cancel_order(self, broker_ticket: str) -> OrderResult:
        """Cancel a pending order via `TRADE_ACTION_REMOVE`.

        Args:
            broker_ticket: The pending order ticket to cancel.

        Returns:
            An `OrderResult` reflecting the broker's response.
        """
        import MetaTrader5 as mt5  # noqa: N813

        mt5_request: dict[str, object] = {
            "action": mt5.TRADE_ACTION_REMOVE,
            "order": int(broker_ticket),
        }
        result = mt5.order_send(mt5_request)
        return self._to_order_result(result)

    @staticmethod
    def _to_order_result(result: Any) -> OrderResult:
        import MetaTrader5 as mt5  # noqa: N813

        if result is None:
            return OrderResult(
                success=False,
                broker_ticket=None,
                filled_price=None,
                error_message=f"order_send() returned None: {mt5.last_error()}",
            )
        success = result.retcode == mt5.TRADE_RETCODE_DONE
        return OrderResult(
            success=success,
            broker_ticket=str(result.order) if result.order else None,
            filled_price=result.price if success else None,
            error_message=None if success else f"retcode={result.retcode}: {result.comment}",
        )
