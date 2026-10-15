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
provider-activation pattern (DATA_COLLECTION_ENGINE.md). Verified live
during Phase 20 against a MetaQuotes demo account. The `MetaTrader5`
package is imported lazily so this module — and the interface/dataclasses
below — remain importable and testable without the package installed.

Two things were empirically required for reliable live operation on
Windows, found through live diagnosis against a real terminal — not
assumed:

1. **Event loop policy.** `MetaTrader5.initialize()` (and every other
   call) reliably failed with `IPC timeout` (-10005) whenever *any*
   `asyncio` event loop was active in the process, with no event loop at
   all succeeding immediately every time. Root cause: Windows' default
   `ProactorEventLoop` uses I/O Completion Ports (IOCP) internally, which
   collides with the `MetaTrader5` package's own IOCP-based named-pipe
   IPC to the terminal. Switching to `WindowsSelectorEventLoopPolicy`
   (via `configure_event_loop_policy()` below, called once before the
   first event loop is created in the process) resolved it completely
   and reproducibly. Must be called by every entrypoint that will use
   `RealMT5Client` (see `src/bootstrap.py`, `scripts/mt5_historical_backfill.py`).
2. **Same thread as the event loop.** Even with the correct policy,
   wrapping `MetaTrader5` calls in `asyncio.to_thread()` (the usual fix
   for blocking C-extension calls in async code) reintroduced the exact
   same `IPC timeout` — the package appears to have a thread-affinity
   requirement incompatible with being invoked from a worker thread.
   Every call here therefore runs directly on the event loop's own
   thread, at the cost of blocking other concurrent work (Telegram
   sends, DB writes, ...) for the call's duration — a real, accepted
   trade-off, not an oversight.

A third fix, found the same way: `OrderRequest.volume`/`PositionSizeResult.
position_size_units` are in the platform's own risk-sizing unit (ounces
for XAUUSD — the same unit as `entry_price`), but MT5's own `order_send()`
`"volume"` field is in **lots** (1 lot = `symbol_info(...).trade_contract_size`
units — 100oz for this broker's XAUUSD). Passing ounces straight through
would submit an order ~100x too large. `place_order`/`close_position`
convert ounces -> lots via `_ounces_to_lots()` right before calling MT5;
`get_open_positions` converts the other way so `OpenPosition.volume`
stays in the platform's own ounce convention, matching every risk
calculation that reads it (e.g. `src.workflows.market_update.pipeline.
exposure_state_from_positions`).
"""

from __future__ import annotations

import asyncio
import sys
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from src.common.logging import get_logger
from src.settings import Settings, get_settings

logger = get_logger(__name__)

# MT5's local IPC channel has been measured, empirically, to succeed only
# ~40% of the time per attempt against a healthy, already-logged-in
# terminal, with no discernible pattern across event loop policy or
# threading model — a real, unexplained characteristic of this package/
# terminal combination in this environment, not something a single
# process-level fix resolves (MT5_ENGINE.md "Reconnection": "Automatically
# Reconnect"). At a 60% per-attempt failure rate, 8 attempts brings the
# cumulative failure probability under 2%.
_CONNECT_MAX_ATTEMPTS = 8
_CONNECT_RETRY_BASE_DELAY_SECONDS = 1.5

# The same IPC flakiness affects every other call, not just `initialize()`
# (an institutional audit finding: reads had no retry at all). A lighter
# budget than `connect()`'s here keeps one flaky read from stalling a
# hot-path market-scan/journal cycle, while still absorbing the
# documented transient-`None` failure mode.
_READ_MAX_ATTEMPTS = 3
_READ_RETRY_BASE_DELAY_SECONDS = 0.5

# Plausible range for `trade_contract_size` across the instruments this
# platform trades (100 for XAUUSD/XAGUSD-style metals, 100000 for a
# standard FX lot, etc.) -- wide enough to never reject a real
# instrument's genuine contract size, narrow enough to catch the
# near-zero garbage a corrupted IPC read produced in production (see
# `_contract_size`).
_MIN_PLAUSIBLE_CONTRACT_SIZE = 1.0
_MAX_PLAUSIBLE_CONTRACT_SIZE = 100_000.0

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

# Production incident: a single transient IPC glitch in `symbol_info()`
# (the same documented flakiness `_contract_size`/`_normalize_volume`
# already retry for) corrupted the broker-reported `volume_min`
# (read as 3.0, nonsensical for XAUUSD), silently clamping a correctly-
# sized ~0.08-lot risk-based order up to 3.0 lots -- an unmanaged,
# oversized position that sat open with no corresponding journal row
# for the lifetime of the position, since the broker-side retcode was
# still 0 (success). Retrying the read reduces how often this happens
# but can never prove it to zero, so this is the deterministic
# backstop: normalization may only ever move the requested size by a
# small, bounded multiple -- anything beyond that multiple AND large
# enough in absolute terms to matter means the broker-reported limits
# themselves are unreliable this cycle, so the order is refused rather
# than trusted.
#
# `_MAX_PLAUSIBLE_MINIMUM_CLAMP_LOTS` exists so this never rejects the
# everyday, legitimate case: a small account's risk-based size landing
# below the broker's own genuinely tiny minimum (e.g. 0.01 lots for
# XAUUSD) gets clamped up to that real minimum, which can easily be a
# large *ratio* (a 0.0008-lot request clamped to 0.01 is 12x) without
# being wrong -- no real single-instrument minimum is ever a large
# absolute lot size, so only a clamp target *larger* than any plausible
# minimum, reached via a *large* ratio, is treated as corruption.
_MAX_VOLUME_INFLATION_MULTIPLE = 5.0
_MAX_PLAUSIBLE_MINIMUM_CLAMP_LOTS = 0.5


def configure_event_loop_policy() -> None:
    """Configure the process-wide asyncio event loop policy for MT5 compatibility.

    Must be called once, before the first `asyncio.run()` (or any other
    event loop creation) in a process that will use `RealMT5Client` — the
    event loop policy is process-global and cannot be changed once a loop
    already exists. See this module's docstring for why: Windows'
    default `ProactorEventLoop` conflicts with `MetaTrader5`'s own
    IOCP-based IPC, causing every call to fail with `IPC timeout`. A
    no-op on non-Windows platforms, where `RealMT5Client` cannot run anyway.
    """
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


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


@dataclass(frozen=True, slots=True)
class SymbolTick:
    """Current bid/ask quote for a symbol."""

    bid: float
    ask: float
    timestamp: datetime


@dataclass(frozen=True, slots=True)
class OpenPosition:
    """One currently open position on the account.

    Attributes:
        ticket: Broker-assigned position ticket.
        symbol: Broker symbol name.
        direction: "buy" or "sell".
        volume: Current position size.
        entry_price: Original entry (open) price.
        stop_loss: Current protective stop price.
        take_profit: Current target price, if set.
        current_price: Current market price for this position's direction.
        profit: Current floating profit/loss, in account currency.
        magic_number: Strategy identifier the position was opened with.
        opened_at: When the position was opened (broker-reported, UTC).
    """

    ticket: str
    symbol: str
    direction: Literal["buy", "sell"]
    volume: float
    entry_price: float
    stop_loss: float
    take_profit: float | None
    current_price: float
    profit: float
    magic_number: int
    opened_at: datetime


@dataclass(frozen=True, slots=True)
class OrderBookLevel:
    """One price level of a Depth of Market snapshot.

    Attributes:
        price: The level's price.
        volume: Resting volume at this level, in the broker's own units.
        side: "bid" (buy-side resting orders) or "ask" (sell-side).
    """

    price: float
    volume: float
    side: Literal["bid", "ask"]


@dataclass(frozen=True, slots=True)
class OrderBookSnapshot:
    """A single point-in-time Depth of Market snapshot for one symbol.

    MT5's `market_book_get()` only ever exposes the *current* book — there
    is no historical DOM API — so every snapshot is necessarily a live
    read, never reconstructed from storage.

    Attributes:
        symbol: Broker symbol name.
        timestamp: When this snapshot was read (UTC).
        levels: Every level MT5 reported, both sides, in the order MT5
            returned them (typically asks descending then bids descending).
    """

    symbol: str
    timestamp: datetime
    levels: list[OrderBookLevel]


class MT5Client(ABC):
    """Execution gateway interface (MT5_ENGINE.md "Primary Responsibilities")."""

    @abstractmethod
    async def get_order_book(self, symbol: str) -> OrderBookSnapshot | None:
        """Fetch the current Depth of Market snapshot for a symbol, if available.

        Args:
            symbol: Broker symbol name.

        Returns:
            An `OrderBookSnapshot`, or None if this broker/symbol does not
            provide DOM data — callers must fall back to synthetic order
            flow analysis in that case
            (`src.engines.order_flow_engine.synthetic_order_flow`), never
            fabricate a book.
        """

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

    @abstractmethod
    async def get_candles(self, symbol: str, timeframe: str, count: int) -> list[dict[str, Any]]:
        """Fetch the most recent OHLCV bars for a symbol/timeframe.

        Args:
            symbol: Broker symbol name, e.g. "XAUUSD".
            timeframe: One of `src.models.candle.TIMEFRAMES`.
            count: Number of most recent bars to fetch.

        Returns:
            Raw bar dicts (MT5's own field names), ordered oldest first,
            most recent bar last. Empty if no data is available.
        """

    @abstractmethod
    async def get_symbol_tick(self, symbol: str) -> SymbolTick:
        """Fetch the current bid/ask quote for a symbol."""

    @abstractmethod
    async def get_open_positions(
        self, *, symbol: str | None = None, magic_number: int | None = None
    ) -> list[OpenPosition]:
        """Fetch every currently open position, optionally filtered.

        Args:
            symbol: If given, only positions for this symbol.
            magic_number: If given, only positions opened with this magic
                number (i.e. by this platform's own strategies).
        """


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

        Retries `MetaTrader5.initialize()` a few times with backoff before
        giving up, since the local IPC channel has been observed to time
        out transiently even against a healthy terminal.

        Returns:
            True if `MetaTrader5.initialize()` succeeded within
            `_CONNECT_MAX_ATTEMPTS` attempts.
        """
        import MetaTrader5 as mt5  # noqa: N813 - matches the package's own casing

        credentials = self._settings.mt5_env
        # `MetaTrader5.initialize()` treats an explicitly-passed `path=None`
        # as an invalid argument (retcode -2), not as "unset" — unlike most
        # of this package's other optional parameters. Every optional
        # argument is therefore only included in the call when configured,
        # never passed as an explicit `None`.
        init_kwargs: dict[str, object] = {"timeout": 20000}
        if credentials.terminal_path:
            init_kwargs["path"] = credentials.terminal_path
        if credentials.login:
            init_kwargs["login"] = int(credentials.login)
        if credentials.password.get_secret_value():
            init_kwargs["password"] = credentials.password.get_secret_value()
        if credentials.server:
            init_kwargs["server"] = credentials.server

        for attempt in range(1, _CONNECT_MAX_ATTEMPTS + 1):
            initialized = mt5.initialize(**init_kwargs)
            if initialized:
                self._connected = True
                return True
            # `mt5.initialize()` returning False on its own gives no
            # indication of *why* (wrong login, terminal not running,
            # another process already holding the local IPC channel,
            # etc.) -- `mt5.last_error()` carries the terminal's own
            # reported reason, logged here so a failed startup is
            # diagnosable from `live_loop_startup_failed` alone rather
            # than requiring a manual reproduction.
            logger.warning(
                "mt5_initialize_attempt_failed",
                attempt=attempt,
                max_attempts=_CONNECT_MAX_ATTEMPTS,
                last_error=mt5.last_error(),
            )
            if attempt < _CONNECT_MAX_ATTEMPTS:
                await asyncio.sleep(_CONNECT_RETRY_BASE_DELAY_SECONDS * attempt)

        self._connected = False
        return False

    async def is_connected(self) -> bool:
        """Return the last-known connection state from `connect()`."""
        return self._connected

    @staticmethod
    async def _call_with_retry(
        call: Callable[[], Any], *, is_valid: Callable[[Any], bool] | None = None
    ) -> Any:
        """Retry a flaky MT5 read a few times before treating a bad result as real.

        Per this module's docstring, MT5's local IPC channel fails
        transiently on any given call, not just `initialize()`. Every
        `None`-on-failure read method below routes through this so a
        single transient IPC blip mid-cycle doesn't abort a whole
        market-scan/journal cycle.

        Args:
            call: A zero-arg callable wrapping one `MetaTrader5` function call.
            is_valid: Extra plausibility check beyond "not None". Production
                incident: a `symbol_info()` struct came back *non-None*
                with a `trade_contract_size` field read as a near-zero
                garbage value (not `None`, so the old None-only check
                accepted it) -- this lets a caller catch that case too by
                retrying a non-`None` but implausible result the same way
                as an outright failure.

        Returns:
            The first result that is not `None` and passes `is_valid` (if
            given), or the raw `None`/last-attempt result if every
            attempt failed that bar. A genuinely empty (but non-`None`)
            result — e.g. no open positions — is returned immediately
            without wasting further attempts when no `is_valid` is given.
        """
        result: Any = None
        for attempt in range(1, _READ_MAX_ATTEMPTS + 1):
            result = call()
            if result is not None and (is_valid is None or is_valid(result)):
                return result
            if attempt < _READ_MAX_ATTEMPTS:
                await asyncio.sleep(_READ_RETRY_BASE_DELAY_SECONDS * attempt)
        return result

    async def get_account_info(self) -> AccountInfo:
        """Fetch account state via `MetaTrader5.account_info()`.

        Returns:
            The current `AccountInfo`.

        Raises:
            ConnectionError: If the terminal returned no account info
                (not connected/authenticated).
        """
        import MetaTrader5 as mt5  # noqa: N813

        info = await self._call_with_retry(mt5.account_info)
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

    async def _contract_size(self, mt5: Any, symbol: str) -> float | None:
        """Look up `trade_contract_size` (units per 1.0 lot) for a symbol.

        Routed through `_call_with_retry` like every other `symbol_info()`-
        based read in this module, with an added plausibility check.
        Production incident: a single transient IPC glitch returned a
        *non-None* `symbol_info()` struct whose `trade_contract_size`
        field was garbage (a tiny fraction, not the real ~100 for gold).
        The old None-only retry condition accepted it immediately,
        turning a correctly risk-sized ~0.08oz order into one computed
        as ~3 lots -- about 36x too large -- which the broker filled
        without complaint (still a syntactically valid order). Retrying
        on implausible values too, not just `None`, catches this before
        it ever reaches an order request.

        Args:
            mt5: The imported `MetaTrader5` module.
            symbol: Broker symbol name.

        Returns:
            The contract size, or `None` if `symbol_info()` is still
            `None`/implausible after retrying -- callers must treat this
            as "unknown, refuse rather than guess," never silently
            substitute a value that could be wrong by orders of magnitude.
        """

        def _is_plausible(info: Any) -> bool:
            size = info.trade_contract_size
            return (
                bool(size) and _MIN_PLAUSIBLE_CONTRACT_SIZE <= size <= _MAX_PLAUSIBLE_CONTRACT_SIZE
            )

        info = await self._call_with_retry(lambda: mt5.symbol_info(symbol), is_valid=_is_plausible)
        if info is None or not _is_plausible(info):
            return None
        return float(info.trade_contract_size)

    async def _ounces_to_lots(self, mt5: Any, symbol: str, ounces: float) -> float | None:
        """Convert the platform's own risk-sizing unit (ounces) to MT5 lots.

        Returns `None` (never a guessed value) when the contract size
        could not be determined plausibly this cycle.
        """
        contract_size = await self._contract_size(mt5, symbol)
        if contract_size is None:
            return None
        return ounces / contract_size

    async def _normalize_volume(self, mt5: Any, symbol: str, lots: float) -> float:
        """Round and clamp a lot size to the broker's own volume constraints.

        Per MT5_ENGINE.md: "Automatically normalize order volume using
        broker limits... Never fail because of invalid volume." A risk
        calculation can land on a lot size the broker's own
        `volume_step`/`volume_min`/`volume_max` would otherwise reject
        (e.g. 0.017 lots when the step is 0.01) — this rounds to the
        nearest step and clamps into range before the request is ever
        built. Routed through `_call_with_retry` for the same reason as
        `_contract_size`: an unretried transient failure here previously
        skipped the safety clamp entirely rather than retrying for it.

        Args:
            mt5: The imported `MetaTrader5` module.
            symbol: Broker symbol name.
            lots: The raw, unrounded lot size.

        Returns:
            `lots` rounded to the nearest `volume_step` and clamped to
            `[volume_min, volume_max]`. Returns `lots` unchanged if
            `symbol_info()` is still unavailable after retrying, rather
            than fabricating limits.
        """
        info = await self._call_with_retry(lambda: mt5.symbol_info(symbol))
        if info is None or not info.volume_step:
            return lots
        step = float(info.volume_step)
        normalized = round(lots / step) * step
        normalized = max(float(info.volume_min), min(float(info.volume_max), normalized))
        return round(normalized, 8)

    async def _lots_to_ounces(self, mt5: Any, symbol: str, lots: float) -> float:
        """Convert MT5 lots to the platform's own risk-sizing unit (ounces).

        Falls back to `lots` unchanged (mislabeled unit, but never a
        fabricated conversion factor) when the contract size could not
        be determined plausibly this cycle -- this is a read/display
        path, not an order placement, so a wrong display value is a far
        smaller risk than guessing at the real one.
        """
        contract_size = await self._contract_size(mt5, symbol)
        if contract_size is None:
            return lots
        return lots * contract_size

    async def place_order(self, request: OrderRequest) -> OrderResult:
        """Validate then submit an order via `MetaTrader5.order_check()`/`order_send()`.

        Per MT5_ENGINE.md: "Validate every order using order_check()
        before order_send()." A failed pre-flight check is returned
        directly as a failed `OrderResult` without ever calling
        `order_send()` — avoids submitting a request the broker's own
        server-side validation would reject anyway.

        Args:
            request: The order to place. `request.volume` is in the
                platform's own unit (ounces for XAUUSD) and is converted
                to MT5 lots, then rounded/clamped to the broker's own
                `volume_step`/`volume_min`/`volume_max` — see this
                module's docstring.

        Returns:
            An `OrderResult` reflecting the pre-flight check's rejection,
            or the broker's response to the actual order.
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
        raw_lots = await self._ounces_to_lots(mt5, request.symbol, request.volume)
        if raw_lots is None:
            return OrderResult(
                success=False,
                broker_ticket=None,
                filled_price=None,
                error_message=(
                    f"refused to send order for {request.symbol!r}: could not determine "
                    "a plausible contract size this cycle, so the requested "
                    f"{request.volume:.6f} oz cannot be safely converted to lots -- "
                    "refusing rather than guessing"
                ),
            )
        normalized_volume = await self._normalize_volume(mt5, request.symbol, raw_lots)
        if (
            raw_lots > 0
            and normalized_volume > raw_lots * _MAX_VOLUME_INFLATION_MULTIPLE
            and normalized_volume > _MAX_PLAUSIBLE_MINIMUM_CLAMP_LOTS
        ):
            return OrderResult(
                success=False,
                broker_ticket=None,
                filled_price=None,
                error_message=(
                    f"refused to send volume={normalized_volume:.4f} lots: more than "
                    f"{_MAX_VOLUME_INFLATION_MULTIPLE:.0f}x the risk-sized "
                    f"{raw_lots:.6f} lots this order actually requested, and larger than "
                    f"any plausible real minimum ({_MAX_PLAUSIBLE_MINIMUM_CLAMP_LOTS:.2f} "
                    "lots) -- likely a corrupted broker-reported "
                    "volume_min/volume_max/contract_size read rather than this symbol's "
                    "real minimum tradable size"
                ),
            )
        mt5_request: dict[str, object] = {
            "action": mt5.TRADE_ACTION_DEAL if is_market_order else mt5.TRADE_ACTION_PENDING,
            "symbol": request.symbol,
            "volume": normalized_volume,
            "type": order_type_map[request.order_type],
            "sl": request.stop_loss,
            "magic": request.magic_number,
            "comment": request.comment,
        }
        if request.take_profit is not None:
            mt5_request["tp"] = request.take_profit
        if not is_market_order and request.price is not None:
            mt5_request["price"] = request.price

        check_result = mt5.order_check(mt5_request)
        if check_result is None:
            return OrderResult(
                success=False,
                broker_ticket=None,
                filled_price=None,
                error_message=f"order_check() returned None: {mt5.last_error()}",
            )
        if check_result.retcode != 0:
            return OrderResult(
                success=False,
                broker_ticket=None,
                filled_price=None,
                error_message=(
                    f"order_check() rejected: retcode={check_result.retcode}: "
                    f"{check_result.comment}"
                ),
            )

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
            volume: Volume to close, in the platform's own unit (ounces
                for XAUUSD); None closes the full position at MT5's own
                reported lot size (no conversion needed in that case).

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
        # Never close more than the position's own broker-confirmed open
        # volume -- a corrupted `trade_contract_size` read in
        # `_ounces_to_lots` can only ever make a partial close too small
        # (a safe failure, leaving a small remainder) rather than
        # accidentally flipping/over-closing the position. If the
        # conversion can't be done plausibly at all this cycle, fall
        # back to closing the full position -- always a valid, safe
        # operation, unlike guessing at a partial amount.
        close_volume = position.volume
        if volume is not None:
            requested_lots = await self._ounces_to_lots(mt5, position.symbol, volume)
            if requested_lots is not None:
                close_volume = min(requested_lots, position.volume)
        mt5_request: dict[str, object] = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": position.symbol,
            "volume": close_volume,
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

    async def get_candles(self, symbol: str, timeframe: str, count: int) -> list[dict[str, Any]]:
        """Fetch bars via `MetaTrader5.copy_rates_from_pos()`.

        Args:
            symbol: Broker symbol name, e.g. "XAUUSD".
            timeframe: One of `src.models.candle.TIMEFRAMES`.
            count: Number of most recent bars to fetch.

        Returns:
            Raw bar dicts with MT5's own field names ("time", "open",
            "high", "low", "close", "tick_volume", "spread",
            "real_volume"), oldest first. Empty if no data is available.

        Raises:
            ValueError: If `timeframe` has no known MT5 timeframe mapping.
        """
        import MetaTrader5 as mt5  # noqa: N813

        timeframe_map = {
            "M1": mt5.TIMEFRAME_M1,
            "M5": mt5.TIMEFRAME_M5,
            "M15": mt5.TIMEFRAME_M15,
            "M30": mt5.TIMEFRAME_M30,
            "H1": mt5.TIMEFRAME_H1,
            "H4": mt5.TIMEFRAME_H4,
            "D1": mt5.TIMEFRAME_D1,
            "W1": mt5.TIMEFRAME_W1,
            "MN": mt5.TIMEFRAME_MN1,
        }
        mt5_timeframe = timeframe_map.get(timeframe)
        if mt5_timeframe is None:
            raise ValueError(f"Unsupported timeframe for MT5 candles: {timeframe!r}")

        rates = await self._call_with_retry(
            lambda: mt5.copy_rates_from_pos(symbol, mt5_timeframe, 0, count)
        )
        if rates is None:
            return []
        return [
            {
                "time": int(rate["time"]),
                "open": float(rate["open"]),
                "high": float(rate["high"]),
                "low": float(rate["low"]),
                "close": float(rate["close"]),
                "tick_volume": float(rate["tick_volume"]),
                "spread": int(rate["spread"]),
                "real_volume": float(rate["real_volume"]),
            }
            for rate in rates
        ]

    async def get_symbol_tick(self, symbol: str) -> SymbolTick:
        """Fetch the current bid/ask via `MetaTrader5.symbol_info_tick()`.

        Raises:
            ConnectionError: If the terminal returned no tick (symbol
                unavailable or not connected).
        """
        import MetaTrader5 as mt5  # noqa: N813

        tick = await self._call_with_retry(lambda: mt5.symbol_info_tick(symbol))
        if tick is None:
            raise ConnectionError(f"MetaTrader5.symbol_info_tick({symbol!r}) returned None")
        return SymbolTick(
            bid=tick.bid, ask=tick.ask, timestamp=datetime.fromtimestamp(tick.time, tz=UTC)
        )

    async def get_order_book(self, symbol: str) -> OrderBookSnapshot | None:
        """Fetch the current DOM snapshot via `MetaTrader5.market_book_get()`.

        Args:
            symbol: Broker symbol name.

        Returns:
            An `OrderBookSnapshot`, or None if this symbol has no DOM
            subscription available (`market_book_add()` failed) or MT5
            reported no levels — never a fabricated book.
        """
        import MetaTrader5 as mt5  # noqa: N813

        if not mt5.market_book_add(symbol):
            return None
        try:
            book = await self._call_with_retry(lambda: mt5.market_book_get(symbol))
        finally:
            mt5.market_book_release(symbol)

        if not book:
            return None

        levels = [
            OrderBookLevel(
                price=entry.price,
                volume=entry.volume_dbl or float(entry.volume),
                side="bid" if entry.type == mt5.BOOK_TYPE_BUY else "ask",
            )
            for entry in book
            if entry.type in (mt5.BOOK_TYPE_BUY, mt5.BOOK_TYPE_SELL)
        ]
        if not levels:
            return None
        return OrderBookSnapshot(symbol=symbol, timestamp=datetime.now(UTC), levels=levels)

    async def get_open_positions(
        self, *, symbol: str | None = None, magic_number: int | None = None
    ) -> list[OpenPosition]:
        """Fetch open positions via `MetaTrader5.positions_get()`.

        Args:
            symbol: If given, only positions for this symbol.
            magic_number: If given, only positions with this magic number.

        Returns:
            Every matching `OpenPosition`, `.volume` converted from MT5
            lots to the platform's own unit (ounces for XAUUSD).
        """
        import MetaTrader5 as mt5  # noqa: N813

        positions = await self._call_with_retry(
            lambda: mt5.positions_get(symbol=symbol) if symbol else mt5.positions_get()
        )
        if not positions:
            return []

        open_positions = [
            OpenPosition(
                ticket=str(position.ticket),
                symbol=position.symbol,
                direction="buy" if position.type == mt5.ORDER_TYPE_BUY else "sell",
                volume=await self._lots_to_ounces(mt5, position.symbol, position.volume),
                entry_price=position.price_open,
                stop_loss=position.sl,
                take_profit=position.tp or None,
                current_price=position.price_current,
                profit=position.profit,
                magic_number=position.magic,
                opened_at=datetime.fromtimestamp(position.time, tz=UTC),
            )
            for position in positions
        ]
        if magic_number is not None:
            open_positions = [p for p in open_positions if p.magic_number == magic_number]
        return open_positions

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
