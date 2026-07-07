# EXECUTION_ENGINE.md

# GOLD QUANT AI

Version: 1.0

---

# PURPOSE

The Execution Engine is responsible for executing, managing and closing positions.

It never creates trading ideas.

It only executes approved decisions from the Chief AI after Risk Engine approval.

Execution quality is considered part of the strategy.

Poor execution destroys statistical edge.

---

# CORE PRINCIPLES

Never execute without approval.

Never execute incomplete signals.

Never modify trade logic.

Never average losing positions automatically.

Never remove protective stops.

Always verify market conditions immediately before execution.

---

# EXECUTION PIPELINE

Chief AI

↓

Risk Approval

↓

Market Validation

↓

Broker Validation

↓

Spread Validation

↓

Liquidity Validation

↓

Execution Decision

↓

Position Monitoring

↓

Trade Management

↓

Position Close

↓

Trade Report

↓

Learning Engine

---

# PRE-EXECUTION CHECKLIST

Before every order verify

Market Open

Connection Status

Broker Connection

Current Spread

Current Slippage

Market Volatility

Upcoming News

Session

Latency

Available Margin

Account Health

Existing Positions

Portfolio Exposure

If any critical check fails

Abort execution.

---

# MARKET SESSION

Detect

Sydney

Tokyo

London

New York

London/New York Overlap

Holiday Sessions

Low Liquidity Periods

Weekend

Determine

Expected Liquidity

Expected Volatility

Expected Spread

Execution Quality

---

# SPREAD VALIDATION

Calculate

Current Spread

Average Spread

Historical Spread

Spread Expansion

Spread Compression

Reject execution if spread exceeds configured thresholds.

---

# SLIPPAGE CONTROL

Estimate

Expected Slippage

Maximum Allowed Slippage

Historical Slippage

Execution Delay

Actual Slippage

Store all values.

---

# ORDER TYPES

Support

Market Order

Buy Limit

Sell Limit

Buy Stop

Sell Stop

Buy Stop Limit

Sell Stop Limit

Partial Close

Position Modification

Position Close

---

# ENTRY VALIDATION

Verify

Entry Price

Distance to Invalidation

Distance to Target

Spread

ATR

Liquidity

Order Block

Execution Zone

Historical Similarity

Expected Reward

If quality deteriorates

Cancel execution.

---

# PROTECTIVE STOP

Place immediately after execution.

The stop is placed according to

Market Structure

Volatility

Invalidation Logic

Liquidity

ATR

Never remove stop.

Never widen stop after execution.

---

# TAKE PROFIT

Calculate dynamically.

Possible methods

Liquidity Targets

Swing High

Swing Low

Volume Profile

Historical Projection

Expected Move

Volatility Projection

Multiple targets supported.

---

# POSITION MANAGEMENT

Monitor continuously

Price

Volume

Volatility

Spread

Liquidity

News

Macro Events

Correlation

Market Structure

Historical Similarity

---

# TRADE MANAGEMENT

Evaluate

Continue Holding

Move Protective Stop

Partial Close

Full Close

Reduce Exposure

No Action

Decision must always be supported by current market evidence.

---

# BREAK EVEN

Move to break-even only when

Risk has materially decreased

Market Structure confirms

Historical continuation probability remains favorable

Do not move automatically after fixed profit.

---

# TRAILING LOGIC

Available trailing methods

Structure

ATR

Swing Points

Liquidity

VWAP

Order Blocks

Adaptive Hybrid

The engine selects the appropriate trailing model based on current market conditions.

---

# PARTIAL CLOSE

Possible actions

No Partial

25%

33%

50%

75%

Dynamic

Decision depends on

Trend Strength

Momentum

Liquidity

Volatility

Historical Continuation Probability

---

# EARLY EXIT CONDITIONS

Exit may occur before target if

Market Structure breaks

Macro changes significantly

Unexpected high-impact news

Correlation changes materially

Liquidity conditions deteriorate

Chief AI confidence falls below minimum threshold

Risk Engine requests exit

---

# FORCE EXIT CONDITIONS

Immediately close if

Broker rejects modifications

Critical system failure

Connection instability

Data integrity compromised

Manual user request

Emergency shutdown

---

# ORDER MONITORING

Monitor

Execution Time

Fill Quality

Partial Fill

Rejected Orders

Broker Response

Network Latency

Every event is logged.

---

# JOURNAL

Store

Timestamp

Direction

Entry

Exit

Stop

Targets

Position Size

Execution Time

Spread

Slippage

Market Session

Confidence

Reason

Supporting Factors

Opposing Factors

Result

Lessons Learned

---

# TELEGRAM REPORT

After execution send

Trade ID

Direction

Entry

Protective Stop

Target(s)

Confidence

Risk

Expected Holding Time

Summary

After closing send

Exit Price

Profit/Loss

Reason for Exit

Trade Duration

Management Quality

Prediction Accuracy

Learning Notes

---

# PERFORMANCE METRICS

Measure

Fill Rate

Average Slippage

Execution Delay

Average Spread

Modification Success Rate

Trade Duration

Exit Efficiency

Management Efficiency

Store permanently.

---

# FAILURE RECOVERY

If execution fails

Retry only when safe.

Never duplicate orders.

Never open multiple unintended positions.

Every retry must be logged.

---

# CHIEF AI INTERFACE

Execution Engine receives

Structured Trade Request

Returns

Execution Status

Order ID

Execution Quality

Fill Information

Current Position State

Monitoring Status

Final Trade Report

---

# FINAL RULE

The Execution Engine must never make trading decisions.

Its responsibility is to execute approved strategies with the highest possible quality, minimize execution errors, preserve the statistical edge identified by the research system, and provide complete transparency for every action.