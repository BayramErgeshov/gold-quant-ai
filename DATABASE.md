# DATABASE.md

# GOLD QUANT AI

Version: 1.0

---

# PURPOSE

The Database is the memory of the platform.

Nothing important may be lost.

Every prediction.

Every trade.

Every book.

Every market event.

Every experiment.

Every hypothesis.

Every improvement.

Everything must be stored.

Everything must be searchable.

Everything must be versioned.

---

# DATABASE PHILOSOPHY

The database is divided into multiple layers.

PostgreSQL

↓

Structured Data

Qdrant

↓

Vector Knowledge

Redis

↓

Temporary Memory

File Storage

↓

Large Documents

---

# POSTGRESQL

Stores

Users

Trades

Predictions

Signals

Orders

Historical Prices

Economic Calendar

News

Statistics

Market Regimes

Sessions

Performance

Research

Books

Embeddings Metadata

Learning Reports

System Logs

Strategy Versions

Approvals

Alerts

Tasks

Agent Results

Agent Health

Execution History

Risk Reports

---

# MAIN TABLES

users

accounts

markets

symbols

candles

ticks

sessions

economic_events

news_events

books

book_chunks

research_papers

signals

predictions

trades

orders

positions

executions

risk_reports

technical_reports

macro_reports

news_reports

ml_reports

historical_similarity

market_regimes

learning_reports

feature_importance

strategy_versions

hypotheses

validation_results

agent_logs

system_logs

telegram_messages

daily_reports

weekly_reports

monthly_reports

tasks

approvals

---

# CANDLES

Store

Timestamp

Open

High

Low

Close

Volume

Spread

Symbol

Timeframe

Session

Volatility

Trend

Liquidity

Regime

News Flag

Macro Flag

---

# SIGNALS

Store

Signal ID

Timestamp

Direction

Entry

Stop

Targets

Confidence

Technical Score

Macro Score

News Score

Historical Score

Risk Score

Execution Status

Reason

Alternative Scenario

---

# TRADES

Store

Trade ID

Account

Symbol

Direction

Entry

Exit

Lot Size

Risk

Profit

Loss

Duration

Holding Time

Maximum Drawdown

Maximum Favorable Excursion

Maximum Adverse Excursion

Reason

Journal

Learning ID

---

# PREDICTIONS

Store

Prediction ID

Timestamp

Expected Direction

Expected Probability

Expected Move

Expected Duration

Expected Confidence

Actual Result

Accuracy

Explanation

---

# NEWS

Store

Source

Title

Summary

Category

Importance

Country

Currency

Expected Impact

Actual Impact

Historical Similarity

Confidence

Entities

---

# BOOKS

Store

Title

Author

Edition

Language

Category

Upload Date

Pages

Quality Score

Validation Status

---

# BOOK CHUNKS

Store

Chunk ID

Book ID

Page

Chapter

Section

Embedding ID

Topic

Confidence

Historical Validation

Usage Count

---

# HISTORICAL SIMILARITY

Store

Pattern

Similarity Score

Historical Dates

Outcome

Win Rate

Average Move

Average Duration

Probability

Confidence

---

# LEARNING REPORTS

Store

Trade

Mistake

Improvement

Recommendation

Historical Evidence

Confidence

Approval Status

---

# FEATURE IMPORTANCE

Store

Feature

Current Weight

Historical Weight

Accuracy

Improvement

Decay

Validation

---

# STRATEGY VERSIONING

Every strategy update receives

Version

Date

Reason

Validation

Approval

Rollback Available

Performance

---

# QDRANT

Purpose

Semantic Search

Book Embeddings

Research Embeddings

News Embeddings

Historical Embeddings

Knowledge Embeddings

Trade Embeddings

Journal Embeddings

Pattern Embeddings

Hypothesis Embeddings

---

# REDIS

Stores

Current Sessions

Agent Cache

Temporary Results

Queues

Locks

Scheduler

Market Cache

Live News Cache

---

# FILE STORAGE

Stores

Books

Research Papers

PDF

Charts

Images

Trade Screenshots

Backtests

Reports

Logs

Exports

---

# BACKUP

Automatic

Hourly

Daily

Weekly

Monthly

Versioned

Encrypted

Integrity Checked

---

# AUDIT

Every change

Timestamp

User

Agent

Reason

Old Value

New Value

Approval

Rollback Point

---

# PERFORMANCE

Database must support

Millions of candles

Millions of news

Millions of embeddings

Millions of signals

Millions of trades

Without performance degradation.

---

# DATA RETENTION

Never delete

Trades

Research

Books

Historical Data

Learning Reports

Instead

Archive

Compress

Index

Version

---

# DATA QUALITY

Every record must include

Timestamp

Source

Confidence

Validation Status

Integrity Check

Version

Nothing enters production without validation.

---

# FINAL RULE

The database is the institutional memory of GOLD QUANT AI.

If information can help future research, validation, learning or auditing, it must be stored.

No important knowledge should ever be lost.