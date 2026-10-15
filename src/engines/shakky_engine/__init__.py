"""Shakky (Classic M5 Strategy Engine).

A completely independent, purely rule-based trading engine -- per its own
production requirement, it must NOT use Chief AI decision logic, the
Trade Quality Engine, Books Intelligence, Machine Learning, Historical
Pattern Matching, the News Engine, the Correlation Engine (except DXY),
Smart Money, Order Flow, or any existing AI scoring/confluence math.
Every module in this package only imports plain, deterministic technical-
analysis functions (EMA/RSI/MACD/ADX/ATR/swing points/candlestick shape
detectors) already shared elsewhere in this codebase, or new plain
functions written here in the same style -- never anything from
`src.engines.chief_ai`, `src.engines.ml_engine`, `src.engines.news_engine`,
`src.engines.historical_engine`, `src.engines.book_engine`, or the AI
agent-confluence layer (`src.core.agents.confluence`).
"""
