# WORKFLOW_ENGINE.md

# GOLD QUANT AI

Version: 1.0

---

# PURPOSE

The Workflow Engine is the central orchestrator of the entire platform.

It controls every AI department.

It decides which agents run.

It schedules research.

It distributes tasks.

It monitors execution.

It guarantees that no important analysis is skipped.

The Workflow Engine never performs analysis itself.

---

# CORE PRINCIPLES

Everything is event driven.

Everything is logged.

Everything is reproducible.

Everything is asynchronous.

Nothing blocks the system.

Every workflow is restartable.

Every workflow has checkpoints.

Every workflow has rollback capability.

---

# GLOBAL WORKFLOW

System Start

↓

Health Check

↓

Connect Services

↓

Load Configuration

↓

Load Memory

↓

Load Knowledge Base

↓

Connect MT5

↓

Connect Telegram

↓

Connect Database

↓

Start Data Collection

↓

Start Research

↓

Begin Live Monitoring

---

# STARTUP WORKFLOW

Verify

Python Environment

Docker

Redis

PostgreSQL

Qdrant

MT5

Telegram

Internet

External APIs

Scheduler

Logging

If any critical dependency fails

Do not trade.

Continue diagnostics.

---

# MARKET UPDATE WORKFLOW

Tick Received

↓

Update Database

↓

Update Cache

↓

Update Indicators

↓

Update Market Structure

↓

Update Liquidity

↓

Update Volatility

↓

Update Sessions

↓

Trigger Technical Analysis

↓

Trigger Macro Validation

↓

Trigger Historical Similarity

↓

Trigger ML

↓

Trigger Chief AI

---

# NEWS WORKFLOW

Breaking News

↓

Collect Article

↓

Verify Source

↓

Remove Duplicates

↓

Extract Entities

↓

Estimate Importance

↓

Search Historical Analogues

↓

Update Macro Context

↓

Notify Chief AI

↓

Telegram Alert

↓

Store

---

# BOOK WORKFLOW

User Upload

↓

OCR

↓

Clean

↓

Split

↓

Embedding

↓

Topic Classification

↓

Knowledge Graph

↓

Store Qdrant

↓

Historical Validation Queue

↓

Knowledge Ready

---

# HISTORICAL WORKFLOW

Daily

↓

Download Missing Data

↓

Validate

↓

Recalculate Statistics

↓

Update Similarity Index

↓

Update Pattern Database

↓

Update Feature Importance

↓

Store Results

---

# RESEARCH WORKFLOW

Research Queue

↓

Assign Department

↓

Assign Agent

↓

Run Analysis

↓

Generate Report

↓

Store

↓

Chief AI

↓

Learning Engine

---

# SIGNAL WORKFLOW

Chief AI

↓

Consensus

↓

Risk Validation

↓

Execution Validation

↓

Telegram Preview

↓

MT5 Execution

↓

Journal

↓

Learning Queue

---

# TRADE MONITORING WORKFLOW

Open Trade

↓

Track Tick

↓

Track Volatility

↓

Track News

↓

Track Liquidity

↓

Track Macro

↓

Track Structure

↓

Update Confidence

↓

Adjust Stop (if approved)

↓

Close Trade

↓

Learning

---

# LEARNING WORKFLOW

Trade Closed

↓

Collect Data

↓

Analyze

↓

Compare Prediction

↓

Compare Reality

↓

Detect Errors

↓

Generate Improvements

↓

Store

↓

Notify User

---

# BACKTEST WORKFLOW

New Strategy

↓

Historical Test

↓

Walk Forward

↓

Monte Carlo

↓

Robustness

↓

Performance

↓

Approval Request

↓

Archive

---

# DAILY WORKFLOW

00:00 UTC

↓

Update Statistics

↓

Update Performance

↓

Update Knowledge

↓

Archive Logs

↓

Daily Report

↓

Telegram

---

# WEEKLY WORKFLOW

Weekend

↓

Recalculate Feature Importance

↓

Recalculate Agent Rankings

↓

Update Historical Database

↓

Update Similarity Models

↓

Generate Weekly Report

↓

Research Recommendations

---

# MONTHLY WORKFLOW

Month End

↓

Deep Historical Analysis

↓

Strategy Evaluation

↓

ML Evaluation

↓

Database Optimization

↓

Archive

↓

Monthly Report

↓

User Approval Requests

---

# FAILURE WORKFLOW

Failure Detected

↓

Identify Module

↓

Restart Module

↓

Recover State

↓

Validate Data

↓

Resume

↓

Log

↓

Notify

---

# AGENT FAILURE

If one AI agent crashes

Restart only that agent.

Never stop the platform.

Chief AI continues using remaining evidence.

Confidence decreases accordingly.

---

# API FAILURE

API Failure

↓

Retry

↓

Fallback Source

↓

Cache

↓

Historical Estimate

↓

Notify

---

# DATABASE FAILURE

Pause Trading

↓

Continue Research in Memory

↓

Reconnect

↓

Sync Missing Data

↓

Resume

---

# MT5 FAILURE

Disable Execution

Continue Analysis

Continue Research

Continue Learning

Continue Telegram

Resume after reconnect.

---

# TELEGRAM FAILURE

Store Messages

Queue Messages

Reconnect

Deliver Missing Messages

---

# SCHEDULER

Tick Events

M1

M5

M15

M30

H1

H4

Daily

Weekly

Monthly

Custom Events

News Events

Emergency Events

Manual Events

---

# PRIORITY SYSTEM

Priority 1

Emergency

Critical News

Execution

Risk

---

Priority 2

Market Update

Chief AI

Learning

---

Priority 3

Books

Research

Historical

Optimization

---

Priority 4

Reports

Statistics

Maintenance

---

# STATE MANAGEMENT

Every workflow stores

Current State

Completed Steps

Pending Steps

Errors

Timestamp

Responsible Agent

Recovery Point

---

# AUDIT

Every workflow logs

Start

Finish

Duration

Input

Output

Agents Used

Data Sources

Errors

Warnings

Recovery

---

# METRICS

Measure

Workflow Duration

Queue Size

Success Rate

Failure Rate

Recovery Time

Latency

CPU

RAM

Agent Utilization

Research Throughput

---

# FINAL RULE

The Workflow Engine is the operating system of GOLD QUANT AI.

It ensures every department works together as one institutional research organization.

No analysis, trade, learning event or improvement may occur outside a controlled workflow.