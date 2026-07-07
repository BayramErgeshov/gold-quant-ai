"""Standalone MT5 connection diagnostic.

Run with the project's own virtual environment interpreter:

    ./.venv/Scripts/python.exe scripts/mt5_connection_check.py

Verifies that MetaTrader5 is installed in the running interpreter,
initializes a connection using MT5_LOGIN/MT5_PASSWORD/MT5_SERVER from the
environment (never hardcoded), and prints package version, terminal info,
account info and the last error code. Read-only: never places an order or
modifies any account state.
"""

from __future__ import annotations

import os
import sys


def main() -> int:
    print("=== Python interpreter ===")
    print(f"sys.executable: {sys.executable}")
    print(f"sys.version: {sys.version}")

    try:
        import MetaTrader5 as mt5  # noqa: N813 - matches the package's own casing
    except ImportError as exc:
        print(f"FAILED: MetaTrader5 is not importable in this interpreter: {exc}")
        return 1

    print()
    print("=== MetaTrader5 package ===")
    print(f"module file: {mt5.__file__}")
    print(f"module version: {getattr(mt5, '__version__', 'unknown')}")

    login = os.environ.get("MT5_LOGIN", "")
    password = os.environ.get("MT5_PASSWORD", "")
    server = os.environ.get("MT5_SERVER", "")
    if not login or not password or not server:
        print()
        print("FAILED: MT5_LOGIN / MT5_PASSWORD / MT5_SERVER not all set in the environment.")
        return 1

    print()
    print("=== mt5.initialize() ===")
    connected = mt5.initialize(login=int(login), password=password, server=server, timeout=20000)
    print(f"initialize() result: {connected}")

    if not connected:
        print(f"last_error(): {mt5.last_error()}")
        return 1

    try:
        print()
        print("=== mt5.version() ===")
        print(mt5.version())

        print()
        print("=== mt5.terminal_info() ===")
        print(mt5.terminal_info())

        print()
        print("=== mt5.account_info() ===")
        print(mt5.account_info())

        print()
        print("=== mt5.symbol_info('XAUUSD') ===")
        print(mt5.symbol_info("XAUUSD"))

        print()
        print("=== mt5.symbol_info_tick('XAUUSD') ===")
        print(mt5.symbol_info_tick("XAUUSD"))

        print()
        print("=== mt5.last_error() ===")
        print(mt5.last_error())
    finally:
        mt5.shutdown()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
