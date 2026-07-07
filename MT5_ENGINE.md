# MT5_ENGINE.md

# GOLD QUANT AI

Version: 1.0

---

# PURPOSE

The MT5 Engine is responsible for all communication between GOLD QUANT AI and MetaTrader 5.

It must never generate trading ideas.

It only executes approved decisions, synchronizes account information, retrieves market data, and reports execution results.

Every interaction must be logged.

Every order must be traceable.

Every execution must be reproducible.

---

# PRIMARY RESPONSIBILITIES

Connect to MT5

Authenticate

Monitor Connection

Download Historical Data

Receive Live Quotes

Receive Tick Data

Receive Candle Data

Read Account Information

Read Open Positions

Read Orders

Read Trade History

Execute Orders

Modify Orders

Close Orders

Monitor Positions

Recover From Errors

Synchronize Database

---

# INITIAL MODE

The system starts ONLY in

Demo Mode

Live Mode is disabled.

The user must explicitly enable Live Mode.

---

# CONNECTION

Supported

MetaTrader 5 Terminal

Python MetaTrader5 API

Dedicated VPS

Multiple Accounts

---

# CONNECTION VALIDATION

Before every operation verify

Terminal Running

Connection Alive

Broker Connected

Trading Allowed

Market Open

Correct Account

Correct Symbol

Correct Time

Correct Leverage

Correct Permissions

---

# ACCOUNT INFORMATION

Continuously synchronize

Account Number

Broker

Server

Balance

Equity

Margin

Free Margin

Margin Level

Currency

Leverage

Account Type

Demo / Live

Trading Permission

---

# MARKET DATA

Download

Ticks

M1

M5

M15

M30

H1

H4

D1

W1

MN

Bid

Ask

Spread

Volume

Real Volume

Time

Store permanently.

---

# HISTORICAL DOWNLOAD

On first startup

Download maximum available history.

Validate

Missing Candles

Corrupted Data

Duplicate Candles

Timezone

Broker Differences

Normalize

Store

---

# LIVE STREAM

Receive

Ticks

Bid

Ask

Spread

Execution

Market Status

Reconnect automatically if interrupted.

---

# SYMBOL MANAGEMENT

Initially

XAUUSD

Future support

EURUSD

GBPUSD

USDJPY

Indices

Crypto

Commodities

Architecture must support expansion.

---

# ORDER EXECUTION

Supported

BUY

SELL

BUY LIMIT

SELL LIMIT

BUY STOP

SELL STOP

BUY STOP LIMIT

SELL STOP LIMIT

Close Position

Partial Close

Modify Position

Cancel Order

---

# EXECUTION VALIDATION

Before sending order verify

Spread

ATR

Session

Margin

Account Status

Confidence

Risk Approval

Chief AI Approval

Execution Window

---

# ORDER PARAMETERS

Every order contains

Symbol

Direction

Volume

Entry

Protective Stop

Take Profit

Magic Number

Comment

Trade ID

Strategy Version

Journal ID

---

# MAGIC NUMBER

Every strategy receives

Unique Magic Number

Every order is linked to

Strategy

Agent

Prediction

Learning Record

Journal

---

# POSITION MONITORING

Continuously monitor

Current Price

Floating Profit

Floating Loss

Spread

Swap

Commission

Current Stop

Current Target

Volatility

News

Macro Events

Market Structure

Confidence

---

# ORDER MODIFICATION

Allowed

Move Stop

Partial Close

Close Trade

Cancel Pending Order

Trailing Stop

Update Comment

Not Allowed

Increase Risk

Remove Protective Stop

Increase Position Size automatically

---

# POSITION CLOSING

Close when

Target reached

Protective Stop reached

Chief AI decision

Risk Engine request

Critical News

Emergency Shutdown

User Request

---

# EMERGENCY MODE

Immediately stop execution if

Broker Offline

Database Failure

Critical API Failure

Repeated Execution Failure

Account Mismatch

Unexpected Live Account

Data Corruption

---

# SYNCHRONIZATION

Every operation updates

PostgreSQL

Redis

Telegram

Journal

Learning Engine

Statistics Engine

---

# EXECUTION LOG

Store

Timestamp

Trade ID

Broker Ticket

Account

Direction

Volume

Entry

Exit

Spread

Slippage

Commission

Swap

Execution Time

Latency

Result

Error

---

# ERROR HANDLING

Handle

Connection Lost

Timeout

Rejected Order

Invalid Volume

Invalid Stops

Market Closed

Trade Disabled

Insufficient Margin

Server Busy

Retry only when safe.

Never duplicate execution.

---

# RECONNECTION

Automatically

Reconnect

Verify Session

Verify Orders

Verify Positions

Verify Database

Resume Monitoring

---

# ACCOUNT SAFETY

Never execute if

Account Type Unknown

Account Number Changed

Live Account Not Approved

Incorrect Symbol

Risk Engine Rejected

Chief AI Rejected

---

# MULTI ACCOUNT SUPPORT

Architecture supports

Demo

Paper

Forward Test

Future Live

Each account isolated.

---

# LATENCY

Measure

Ping

Broker Response

Execution Delay

Slippage

Store permanently.

---

# PERFORMANCE METRICS

Track

Average Execution Time

Average Slippage

Average Spread

Order Success Rate

Connection Stability

Execution Quality

Broker Reliability

---

# TELEGRAM INTEGRATION

Notify

Connection Established

Connection Lost

Order Sent

Order Filled

Order Modified

Trade Closed

Execution Error

Emergency Stop

Account Warning

---

# SECURITY

Never expose

Passwords

API Keys

Broker Credentials

Session Tokens

Sensitive Data

All credentials encrypted.

---

# FINAL RULE

The MT5 Engine is an execution gateway.

It never analyzes the market.

It never predicts price.

It only executes validated institutional decisions with maximum reliability, safety, transparency and traceability.