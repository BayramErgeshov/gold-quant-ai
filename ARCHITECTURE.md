# ARCHITECTURE.md

# GOLD QUANT AI

Version: 1.0

---

# SYSTEM OVERVIEW

The platform is built as an institutional multi-agent architecture.

Every subsystem is independent.

Every subsystem has one responsibility.

Every subsystem communicates through well-defined interfaces.

No module may directly depend on implementation details of another module.

The architecture follows:

- Clean Architecture
- Domain Driven Design
- Event Driven Architecture
- Modular Design
- CQRS where appropriate

---

# HIGH LEVEL ARCHITECTURE

```
                         USER

                          │

                    Telegram Bot

                          │

                 Chief Decision AI

──────────────────────────────────────────────

Research Layer

├── Technical Department
├── Macro Department
├── News Department
├── Quant Department
├── Statistical Department
├── Book Department
├── Machine Learning Department
├── Historical Research Department
├── Execution Department
└── Monitoring Department

──────────────────────────────────────────────

Infrastructure Layer

├── PostgreSQL
├── Qdrant
├── Redis
├── MT5
├── Docker
├── Scheduler
├── Logging
├── Monitoring

──────────────────────────────────────────────

External Sources

├── Market Data
├── Economic Calendar
├── News
├── Books
├── Research Papers
├── User Files
└── Historical Data
```

---

# MAIN COMPONENTS

Chief AI

Research Coordinator

Trading Decision Engine

Execution Engine

Learning Engine

Memory Engine

Knowledge Engine

Book Engine

Historical Engine

Risk Engine

Telegram Engine

Monitoring Engine

Logging Engine

Backtesting Engine

Testing Engine

---

# CHIEF AI

Responsibilities

Coordinate every department.

Receive reports.

Evaluate confidence.

Resolve disagreements.

Generate final recommendation.

Approve execution.

Create explanation.

Store decision.

Never analyze charts directly.

Never calculate indicators directly.

Never bypass research agents.

---

# TECHNICAL DEPARTMENT

Contains independent agents.

Each agent studies one discipline.

Examples

Market Structure

Price Action

ICT

Smart Money

Wyckoff

Liquidity

Volume Profile

Order Flow

VWAP

Market Profile

Elliott

Fibonacci

ATR

Trend

Volatility

Support Resistance

Candlestick Analysis

Pattern Recognition

Breakout Analysis

False Breakout Detection

Range Detection

Momentum

Divergence

Every agent works independently.

---

# MACRO DEPARTMENT

Agents

Federal Reserve

ECB

BoJ

PBoC

Inflation

Interest Rates

Employment

GDP

PMI

PPI

CPI

PCE

Bond Yields

Real Yield

Dollar Index

Liquidity Conditions

Geopolitics

Commodity Correlation

Gold Fundamentals

---

# NEWS DEPARTMENT

Responsibilities

Collect news.

Remove duplicates.

Evaluate credibility.

Estimate impact.

Estimate historical importance.

Estimate expected volatility.

Generate structured event reports.

Rank news by relevance.

---

# BOOK DEPARTMENT

Responsibilities

Read books.

Read user documents.

Read research papers.

Chunk documents.

Create embeddings.

Store embeddings.

Answer knowledge requests.

Never produce trading signals.

Only provide knowledge.

---

# HISTORICAL RESEARCH DEPARTMENT

Responsibilities

Analyze every available historical candle.

Classify market regimes.

Classify volatility.

Classify structure.

Build historical database.

Search similar situations.

Generate similarity scores.

---

# MACHINE LEARNING DEPARTMENT

Responsibilities

Train prediction models.

Train classification models.

Train clustering models.

Evaluate models.

Reject weak models.

Monitor drift.

Retrain when approved.

Never deploy automatically.

---

# STATISTICAL DEPARTMENT

Responsibilities

Calculate probabilities.

Evaluate signal quality.

Evaluate confidence.

Measure historical performance.

Measure factor importance.

Measure edge.

Reject statistically weak hypotheses.

---

# EXECUTION DEPARTMENT

Responsibilities

Prepare orders.

Validate parameters.

Validate account.

Validate spread.

Validate slippage.

Validate session.

Execute.

Monitor.

Modify protective stop if strategy requires.

Close positions when exit conditions are met.

Generate execution report.

---

# RISK DEPARTMENT

Responsibilities

Determine whether trade idea is valid.

Calculate acceptable exposure.

Check portfolio risk.

Check daily risk.

Check weekly risk.

Check volatility.

Check correlation.

Approve or reject execution.

Risk department has veto power.

---

# LEARNING DEPARTMENT

Responsibilities

Monitor prediction quality.

Compare expected vs actual.

Find mistakes.

Generate improvement proposals.

Never modify production logic automatically.

Always request approval.

---

# MEMORY DEPARTMENT

Long-term memory.

Short-term memory.

Trade memory.

Research memory.

Book memory.

News memory.

Market memory.

Error memory.

Hypothesis memory.

Validation memory.

---

# TELEGRAM DEPARTMENT

Responsibilities

Trade notifications.

Research summaries.

Daily reports.

Weekly reports.

Monthly reports.

Performance reports.

System alerts.

Learning proposals.

---

# DATABASE LAYER

PostgreSQL

Stores

Trades

Signals

Predictions

Statistics

Users

Strategies

Logs

Market snapshots

Research

Approvals

System state

---

Qdrant

Stores

Book embeddings

Research embeddings

Historical embeddings

News embeddings

Knowledge embeddings

---

Redis

Stores

Queues

Cache

Temporary memory

Sessions

Agent communication

---

# AGENT COMMUNICATION

Agents never call each other directly.

Communication occurs through:

Chief AI

Message Queue

Event Bus

Shared Memory

Every message is logged.

Every decision is reproducible.

---

# DECISION PIPELINE

Market Update

↓

Research Trigger

↓

Technical Analysis

↓

Macro Analysis

↓

News Analysis

↓

Historical Similarity

↓

Book Knowledge

↓

Machine Learning

↓

Statistics

↓

Risk Analysis

↓

Chief AI

↓

Final Recommendation

↓

Execution Decision

↓

Trade Monitoring

↓

Journal

↓

Learning

↓

Knowledge Update

---

# FAILURE HANDLING

If one agent fails

Restart only that agent.

Never stop entire platform.

If external data unavailable

Use remaining validated data.

If confidence drops

Reduce recommendations.

If critical systems fail

Disable execution.

Continue research.

---

# OBSERVABILITY

Every event logged.

Every prediction stored.

Every explanation stored.

Every trade stored.

Every improvement stored.

Everything reproducible.

Nothing hidden.

---

# SCALABILITY

Architecture must support:

New markets.

New agents.

New ML models.

New books.

New APIs.

New brokers.

New databases.

New execution engines.

Without changing the core architecture.

---

# FUTURE EXPANSION

After XAUUSD demonstrates stable performance, architecture should support additional instruments such as major FX pairs, indices or cryptocurrencies through the same modular framework without changing the decision core.