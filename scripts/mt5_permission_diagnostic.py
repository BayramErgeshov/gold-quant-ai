"""MT5 trading permission diagnostic (read-only).

Connects to the configured MT5 terminal and prints every field relevant
to whether an order can be placed: `terminal_info()`, `account_info()`,
`mt5.version()`, `mt5.last_error()`. Then runs `order_check()` for a
minimum-volume BUY on XAUUSD to see exactly what the trade server would
say without ever calling `order_send()` — this script never places,
modifies, or closes a real order.

Run with the project's own virtual environment interpreter:

    PYTHONPATH=. ./.venv/Scripts/python.exe scripts/mt5_permission_diagnostic.py
"""

from __future__ import annotations

import sys

from src.core.execution.mt5_client import configure_event_loop_policy
from src.settings import get_settings


def _print_section(title: str) -> None:
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


def main() -> int:
    configure_event_loop_policy()
    settings = get_settings()
    mt5_symbol = settings.platform.symbols.primary

    import MetaTrader5 as mt5  # noqa: N813 - matches the package's own casing

    credentials = settings.mt5_env
    init_kwargs: dict[str, object] = {"timeout": 20000}
    if credentials.terminal_path:
        init_kwargs["path"] = credentials.terminal_path
    if credentials.login:
        init_kwargs["login"] = int(credentials.login)
    if credentials.password.get_secret_value():
        init_kwargs["password"] = credentials.password.get_secret_value()
    if credentials.server:
        init_kwargs["server"] = credentials.server

    _print_section("Step 1: MetaTrader5.initialize()")
    initialized = mt5.initialize(**init_kwargs)
    print(f"initialize() returned: {initialized}")
    if not initialized:
        print(f"last_error(): {mt5.last_error()}")
        print("ABORTED: could not initialize the terminal connection.")
        return 1

    _print_section("mt5.version()")
    print(mt5.version())

    _print_section("mt5.last_error()")
    print(mt5.last_error())

    _print_section("terminal_info()")
    terminal = mt5.terminal_info()
    if terminal is None:
        print("terminal_info() returned None")
    else:
        terminal_dict = terminal._asdict()
        for key, value in terminal_dict.items():
            print(f"{key}: {value}")
        print()
        print("--- Key trading-permission fields ---")
        print(f"connected: {terminal_dict.get('connected')}")
        print(
            f"trade_allowed (AutoTrading/AlgoTrading toggle): {terminal_dict.get('trade_allowed')}"
        )
        print(f"tradeapi_disabled: {terminal_dict.get('tradeapi_disabled')}")
        print(f"dlls_allowed: {terminal_dict.get('dlls_allowed')}")
        print(f"community_account: {terminal_dict.get('community_account')}")
        print(f"ping_last: {terminal_dict.get('ping_last')}")

    _print_section("account_info()")
    account = mt5.account_info()
    if account is None:
        print("account_info() returned None")
        print(f"last_error(): {mt5.last_error()}")
    else:
        account_dict = account._asdict()
        for key, value in account_dict.items():
            print(f"{key}: {value}")
        print()
        print("--- Key account permission fields ---")
        trade_mode = account_dict.get("trade_mode")
        trade_mode_names = {
            mt5.ACCOUNT_TRADE_MODE_DEMO: "DEMO",
            mt5.ACCOUNT_TRADE_MODE_CONTEST: "CONTEST",
            mt5.ACCOUNT_TRADE_MODE_REAL: "REAL",
        }
        print(f"trade_mode: {trade_mode} ({trade_mode_names.get(trade_mode, 'UNKNOWN')})")
        print(
            f"trade_allowed (server-side account permission): {account_dict.get('trade_allowed')}"
        )
        print(
            f"trade_expert (Expert Advisor trading permission): {account_dict.get('trade_expert')}"
        )
        print(f"limit_orders: {account_dict.get('limit_orders')}")
        print(f"margin_so_mode: {account_dict.get('margin_so_mode')}")

    _print_section(f"Step 2: symbol_info({mt5_symbol!r})")
    symbol_info = mt5.symbol_info(mt5_symbol)
    if symbol_info is None:
        print(f"symbol_info({mt5_symbol!r}) returned None -- symbol not found/not visible.")
        print(f"last_error(): {mt5.last_error()}")
        mt5.shutdown()
        return 1

    if not symbol_info.visible:
        print(f"Symbol {mt5_symbol!r} is not visible in Market Watch; selecting it now.")
        mt5.symbol_select(mt5_symbol, True)
        symbol_info = mt5.symbol_info(mt5_symbol)

    volume_min = float(symbol_info.volume_min)
    trade_mode_names_symbol = {
        mt5.SYMBOL_TRADE_MODE_DISABLED: "DISABLED",
        mt5.SYMBOL_TRADE_MODE_LONGONLY: "LONGONLY",
        mt5.SYMBOL_TRADE_MODE_SHORTONLY: "SHORTONLY",
        mt5.SYMBOL_TRADE_MODE_CLOSEONLY: "CLOSEONLY",
        mt5.SYMBOL_TRADE_MODE_FULL: "FULL",
    }
    print(f"volume_min: {volume_min} lots")
    symbol_trade_mode_name = trade_mode_names_symbol.get(symbol_info.trade_mode, "UNKNOWN")
    print(f"trade_mode: {symbol_info.trade_mode} ({symbol_trade_mode_name})")
    print(f"trade_contract_size: {symbol_info.trade_contract_size}")
    print(f"visible: {symbol_info.visible}")

    tick = mt5.symbol_info_tick(mt5_symbol)
    if tick is None:
        print(f"symbol_info_tick({mt5_symbol!r}) returned None -- no live quote available.")
        print(f"last_error(): {mt5.last_error()}")
        mt5.shutdown()
        return 1
    print(f"current tick: bid={tick.bid} ask={tick.ask}")

    _print_section(
        "Step 3: order_check() for a minimum-volume BUY (NOT order_send -- nothing is placed)"
    )
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": mt5_symbol,
        "volume": volume_min,
        "type": mt5.ORDER_TYPE_BUY,
        "price": tick.ask,
        "type_filling": mt5.ORDER_FILLING_IOC,
        "type_time": mt5.ORDER_TIME_GTC,
        "comment": "diagnostic_order_check",
    }
    print(f"request: {request}")

    check_result = mt5.order_check(request)
    print()
    if check_result is None:
        print("order_check() returned None")
        print(f"last_error(): {mt5.last_error()}")
    else:
        check_dict = check_result._asdict()
        for key, value in check_dict.items():
            if key == "request":
                print(f"{key}: {dict(value._asdict())}")
            else:
                print(f"{key}: {value}")

        _print_section("Explanation")
        retcode = check_dict.get("retcode")
        comment = check_dict.get("comment")
        print(f"retcode: {retcode}")
        print(f"comment: {comment!r}")
        if retcode == mt5.TRADE_RETCODE_DONE or retcode == 0:
            print(
                "-> The order WOULD be accepted: margin, permissions and symbol "
                "trading mode all check out for this minimum-volume BUY."
            )
        else:
            print(
                f"-> The order would be REJECTED (retcode={retcode}). The `comment` "
                "field above is the trade server's own reason. Cross-reference it "
                "with terminal_info()/account_info() above: a `trade_allowed=False` "
                "on either terminal or account, or a non-FULL symbol trade_mode, is "
                "the most common cause of a retcode that isn't TRADE_RETCODE_DONE."
            )

    mt5.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
