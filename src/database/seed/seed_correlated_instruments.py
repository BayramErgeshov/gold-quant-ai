"""Idempotent seed data for the `correlated_instruments` table.

Every entry here was verified against this platform's actual connected
MT5 broker (`mt5.symbols_get()`, checked by `path` — e.g. "Forex\\EURUSD",
"Metals\\XAGUSD", "Nasdaq\\ETF\\GLD" — not by name substring, since this
broker also lists ~12,500 Nasdaq equities whose tickers coincidentally
match commodity/index abbreviations, e.g. "WTI" is W&T Offshore Inc, a
stock, not crude oil). Only instruments with a confirmed real MT5 symbol
get `is_enabled=True`; every other instrument the user's Market
Correlation Engine spec asks for (Treasury/real yields, COT reports,
central bank gold purchases, ETF flows, dollar liquidity, VIX, Brent/WTI/
Natural Gas — none of which this broker offers as a CFD) is still
recorded with `mt5_symbol=None, is_enabled=False` so it is architecturally
ready to activate the moment an external provider (FRED, CFTC, World Gold
Council, TwelveData) is configured, per this platform's existing "reduced
mode" pattern (macro/news engines).

DXY itself has no direct MT5 symbol on this broker either; rather than
leaving it disabled, `src.engines.correlation_engine` computes a
documented proxy from the ingested EURUSD/USDJPY/GBPUSD/USDCHF/USDCAD
prices at query time (see that module), so it is intentionally absent
from this seed list.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from src.common.logging import get_logger
from src.models.correlated_instrument import CorrelatedInstrument
from src.repositories.correlated_instrument_repository import CorrelatedInstrumentRepository

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class _InstrumentSeed:
    name: str
    display_name: str
    mt5_symbol: str | None
    category: str


_SEED_INSTRUMENTS: tuple[_InstrumentSeed, ...] = (
    # Confirmed real MT5 symbols (verified via symbol path, not name guesswork).
    _InstrumentSeed("EURUSD", "Euro vs US Dollar", "EURUSD", "fx"),
    _InstrumentSeed("USDJPY", "US Dollar vs Yen", "USDJPY", "fx"),
    _InstrumentSeed("USDCHF", "US Dollar vs Swiss Franc", "USDCHF", "fx"),
    _InstrumentSeed("GBPUSD", "British Pound vs US Dollar", "GBPUSD", "fx"),
    _InstrumentSeed("USDCAD", "US Dollar vs Canadian Dollar", "USDCAD", "fx"),
    _InstrumentSeed("SILVER", "Silver vs US Dollar", "XAGUSD", "precious_metal"),
    _InstrumentSeed("PLATINUM", "Platinum vs US Dollar", "XPTUSD", "precious_metal"),
    _InstrumentSeed("PALLADIUM", "Palladium vs US Dollar", "XPDUSD", "precious_metal"),
    _InstrumentSeed("SP500", "US SPX 500 Index", "US500", "equity_index"),
    _InstrumentSeed("DOW_JONES", "US Wall Street 30 Index", "US30", "equity_index"),
    _InstrumentSeed("NASDAQ", "US Tech 100 Index", "USTEC", "equity_index"),
    _InstrumentSeed("RUSSELL2000", "US Small Cap 2000 Index", "US2000", "equity_index"),
    _InstrumentSeed("GLD_ETF", "SPDR Gold Shares ETF", "GLD", "etf"),
    _InstrumentSeed("IAU_ETF", "iShares Gold Trust ETF", "IAU", "etf"),
    _InstrumentSeed("BITCOIN", "Bitcoin (ETF proxy)", "BTC", "crypto"),
    _InstrumentSeed("ETHEREUM", "Ethereum (ETF proxy)", "ETH", "crypto"),
    # No MT5 symbol on this broker; pending an external data provider.
    _InstrumentSeed("BRENT", "Brent Crude Oil", None, "energy"),
    _InstrumentSeed("WTI", "WTI Crude Oil", None, "energy"),
    _InstrumentSeed("NATURAL_GAS", "Henry Hub Natural Gas", None, "energy"),
    _InstrumentSeed("VIX", "CBOE Volatility Index", None, "volatility"),
    _InstrumentSeed("US_2Y_YIELD", "US 2-Year Treasury Yield", None, "rates"),
    _InstrumentSeed("US_10Y_YIELD", "US 10-Year Treasury Yield", None, "rates"),
    _InstrumentSeed("REAL_YIELDS", "US 10-Year TIPS Real Yield", None, "rates"),
    _InstrumentSeed("COT_REPORTS", "CFTC Commitment of Traders (Gold)", None, "positioning"),
    _InstrumentSeed(
        "CENTRAL_BANK_GOLD_PURCHASES", "Central Bank Gold Purchases (WGC)", None, "positioning"
    ),
    _InstrumentSeed("ETF_FLOWS", "Gold ETF Net Flows", None, "positioning"),
    _InstrumentSeed("DOLLAR_LIQUIDITY", "Global Dollar Liquidity Proxy", None, "rates"),
)


async def seed_correlated_instruments(session: AsyncSession) -> list[CorrelatedInstrument]:
    """Ensure every configured correlated instrument exists in the database.

    Safe to run repeatedly — existing rows are left untouched.

    Args:
        session: An active `AsyncSession`.

    Returns:
        Every existing or newly created `CorrelatedInstrument` row.
    """
    repository = CorrelatedInstrumentRepository(session)
    results: list[CorrelatedInstrument] = []

    for seed in _SEED_INSTRUMENTS:
        existing = await repository.get_by_name(seed.name)
        if existing is not None:
            results.append(existing)
            continue

        created = await repository.add(
            CorrelatedInstrument(
                name=seed.name,
                display_name=seed.display_name,
                mt5_symbol=seed.mt5_symbol,
                category=seed.category,
                is_enabled=seed.mt5_symbol is not None,
            )
        )
        logger.info(
            "correlated_instrument_seeded",
            name=seed.name,
            mt5_symbol=seed.mt5_symbol,
            enabled=created.is_enabled,
        )
        results.append(created)

    return results
