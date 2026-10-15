"""The platform's full independent Technical Department agent roster.

Extracted so every caller that needs "every technical agent" (the live
loop, Market Replay Mode) builds the identical roster instead of each
maintaining its own copy (CODING_STANDARDS.md "Never duplicate
functionality").
"""

from __future__ import annotations

from src.agents.technical.liquidity import LiquidityAgent
from src.agents.technical.market_structure import MarketStructureAgent
from src.agents.technical.momentum import MomentumAgent
from src.agents.technical.price_action import PriceActionAgent
from src.agents.technical.smart_money import SmartMoneyAgent
from src.agents.technical.support_resistance import SupportResistanceAgent
from src.agents.technical.trend import TrendAgent
from src.agents.technical.volatility import VolatilityAgent
from src.core.technical_analysis.agent import TechnicalAgent


def default_technical_agents() -> list[TechnicalAgent]:
    """Build a fresh instance of every independent Technical Department agent."""
    return [
        MarketStructureAgent(),
        TrendAgent(),
        VolatilityAgent(),
        SupportResistanceAgent(),
        LiquidityAgent(),
        SmartMoneyAgent(),
        PriceActionAgent(),
        MomentumAgent(),
    ]
