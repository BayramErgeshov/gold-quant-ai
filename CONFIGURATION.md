# CONFIGURATION.md

# GOLD QUANT AI

Version: 1.0

---

# PURPOSE

This document defines every configurable parameter of GOLD QUANT AI.

No hardcoded values are allowed.

Every threshold must be configurable.

Every configuration change must be versioned.

Every configuration change must be logged.

---

# GLOBAL SETTINGS

Project Name

GOLD QUANT AI

Version

1.0

Environment

Development

Testing

Paper

Demo

Live

Default

Demo

---

# SYMBOLS

Primary

XAUUSD

Secondary

Disabled

Future Expansion

EURUSD

GBPUSD

USDJPY

BTCUSD

ETHUSD

SP500

NASDAQ

US30

DAX

Silver

Oil

---

# TIMEFRAMES

Enabled

MN

W1

D1

H4

H1

M30

M15

M5

M1

Default Execution

M5

Default Context

D1

Primary Structure

H4

---

# ANALYSIS FREQUENCY

Tick

Realtime

M1

Every Candle

M5

Every Candle

M15

Every Candle

H1

Every Candle

Daily

00:00 UTC

Weekly

Sunday

Monthly

First Day

---

# AI DEPARTMENTS

Enable

Chief AI

Technical

Macro

News

Risk

Execution

Historical

Book

ML

Learning

Statistics

Workflow

Monitoring

Database

Telegram

MT5

---

# DATA SOURCES

Market Data

Enabled

News

Enabled

Macro

Enabled

Books

Enabled

Historical

Enabled

Machine Learning

Enabled

Research

Enabled

---

# CONFIDENCE

Minimum Confidence

Configurable

High Confidence

Configurable

Institutional Confidence

Configurable

Emergency Confidence

Configurable

---

# QUALITY

Minimum Grade

Configurable

Maximum Risk Grade

Configurable

Minimum Historical Similarity

Configurable

Minimum Data Quality

Configurable

---

# EXECUTION

Execution Enabled

True

Demo Only

True

Live Enabled

False

Pending Orders

Enabled

Market Orders

Enabled

Partial Close

Enabled

Trailing

Enabled

Break Even

Enabled

---

# RISK

Risk Engine

Mandatory

Risk Profile

Adaptive

Position Size

Dynamic

Exposure

Dynamic

Correlation Filter

Enabled

News Filter

Enabled

Volatility Filter

Enabled

Session Filter

Enabled

---

# TRADE FILTERS

Trend Alignment

Enabled

Liquidity

Enabled

Macro

Enabled

News

Enabled

Historical Similarity

Enabled

Machine Learning

Enabled

Book Validation

Enabled

Risk Validation

Enabled

Execution Validation

Enabled

---

# BOOK ENGINE

Automatic OCR

Enabled

Automatic Chunking

Enabled

Automatic Embeddings

Enabled

Knowledge Graph

Enabled

Validation Required

True

---

# HISTORICAL ENGINE

Download Maximum History

Enabled

Daily Synchronization

Enabled

Similarity Database

Enabled

Pattern Statistics

Enabled

Market Regimes

Enabled

Seasonality

Enabled

---

# MACHINE LEARNING

Enabled

Explainable Models Only

True

Automatic Retraining

False

User Approval

Required

Model Versioning

Enabled

Drift Detection

Enabled

---

# TELEGRAM

Signals

Enabled

Research Reports

Enabled

Learning Reports

Enabled

Trade Journal

Enabled

Daily Reports

Enabled

Weekly Reports

Enabled

Monthly Reports

Enabled

Emergency Alerts

Enabled

---

# LOGGING

Every Event

Enabled

Every Trade

Enabled

Every Prediction

Enabled

Every Decision

Enabled

Every Agent

Enabled

Every Error

Enabled

Every Improvement

Enabled

---

# DATABASE

Auto Backup

Enabled

Hourly

Enabled

Daily

Enabled

Weekly

Enabled

Monthly

Enabled

Compression

Enabled

Integrity Check

Enabled

---

# API

Retry

Enabled

Fallback

Enabled

Caching

Enabled

Health Monitoring

Enabled

Latency Monitoring

Enabled

---

# LEARNING

Continuous Learning

Enabled

Proposal Generation

Enabled

Automatic Deployment

Disabled

Approval Required

True

---

# REPORTS

Trade Report

Enabled

Research Report

Enabled

Prediction Report

Enabled

Market Report

Enabled

Learning Report

Enabled

System Report

Enabled

Performance Report

Enabled

---

# PERFORMANCE

Async Enabled

True

Parallel Agents

Enabled

Dynamic Scheduling

Enabled

Queue System

Enabled

Caching

Enabled

GPU Support

Optional

---

# SECURITY

Secrets Encrypted

Enabled

API Keys Encrypted

Enabled

Database Encryption

Enabled

Audit Logging

Enabled

Access Control

Enabled

Role Based Access

Enabled

---

# FUTURE FEATURES

Voice Interface

Disabled

Web Dashboard

Planned

Mobile App

Planned

Multi Broker

Planned

Portfolio Manager

Planned

Multi Asset

Planned

Institutional Dashboard

Planned

Cloud Deployment

Planned

---

# FINAL RULE

Every configurable value must exist in configuration files.

No production logic may depend on hardcoded constants.

Every configuration change must be logged, versioned and reversible.