# RISK_ENGINE.md

# GOLD QUANT AI

Version: 1.0

---

# PURPOSE

The Risk Engine is the only department responsible for deciding whether a trade may be executed.

No trade may bypass the Risk Engine.

Even if every other department agrees, the Risk Engine may reject the trade.

Capital preservation has higher priority than trade frequency.

The objective is not to maximize the number of trades.

The objective is to maximize long-term risk-adjusted performance.

---

# CORE PRINCIPLES

Protect capital.

Protect consistency.

Protect statistical edge.

Avoid emotional behavior.

Avoid overtrading.

Avoid revenge trading.

Avoid low-quality opportunities.

---

# RISK PHILOSOPHY

Never increase risk after losses.

Never chase the market.

Never average losing positions automatically.

Never remove the protective stop.

Never widen the protective stop after execution.

Every trade must have a predefined invalidation level.

---

# CAPITAL PRESERVATION

The system assumes capital is finite.

Capital is the most valuable asset.

Protecting capital has higher priority than finding trades.

Missing a trade is acceptable.

Taking a statistically weak trade is not.

---

# TRADE APPROVAL PROCESS

Before execution verify

Market Session

↓

Spread

↓

Volatility

↓

Liquidity

↓

Execution Quality

↓

Confidence

↓

Correlation

↓

Portfolio Exposure

↓

News Risk

↓

Macro Risk

↓

Historical Edge

↓

Risk Validation

↓

Approval

---

# CONFIDENCE LEVELS

Confidence

0-40

Reject

---

41-60

Observation only

No execution

---

61-75

Possible setup

Require stronger confirmation

---

76-85

High Quality

Execution allowed

---

86-100

Institutional Grade

Highest Priority

Still requires complete validation.

---

# SIGNAL QUALITY

Every signal receives

Signal Strength

Technical Quality

Macro Quality

News Quality

Historical Quality

Execution Quality

Risk Quality

Overall Grade

AAA

AA

A

BBB

BB

B

C

Trades below minimum accepted grade are rejected.

---

# POSITION SIZING

The Risk Engine calculates position size dynamically.

Inputs

Account Balance

Account Equity

Current Drawdown

Volatility

ATR

Distance to Invalidation

Maximum Allowed Exposure

Market Session

Correlation

Open Positions

Position size must never be fixed.

---

# EXPOSURE CONTROL

Track

Total Exposure

Gold Exposure

USD Exposure

Correlation Exposure

Session Exposure

Daily Exposure

Weekly Exposure

Maximum simultaneous exposure limits are configurable.

---

# DAILY CONTROL

Monitor

Trades Today

Win Rate

Loss Rate

Drawdown

Profit

Execution Quality

Prediction Quality

System Health

Daily statistics are stored permanently.

---

# WEEKLY CONTROL

Track

Weekly Performance

Weekly Drawdown

Prediction Accuracy

Market Regime Changes

Learning Progress

---

# MONTHLY CONTROL

Evaluate

Profit Factor

Sharpe Ratio

Sortino Ratio

Expectancy

Average Win

Average Loss

Maximum Drawdown

Recovery Factor

Signal Accuracy

Strategy Stability

---

# PROTECTIVE STOP

Every trade requires an invalidation level.

The protective stop is placed beyond the point where the original market hypothesis is considered invalid.

Protective stops are determined from market structure and volatility, not arbitrary fixed distances.

The stop must never be moved farther away after entry.

Moving the stop closer is allowed only if supported by the trade management logic.

---

# BREAK EVEN MANAGEMENT

Break-even is not automatic.

Move to break-even only when

Market Structure confirms.

Liquidity has been consumed.

Volatility supports continuation.

Historical probability remains favorable.

Never move to break-even too early.

Avoid unnecessary stop-outs caused by normal market noise.

---

# TRAILING MANAGEMENT

Trailing logic must be adaptive.

Possible trailing methods

Market Structure

ATR

Swing High

Swing Low

VWAP

Liquidity

Order Blocks

Volatility

Historical Behavior

The system chooses the best trailing model according to current market conditions.

---

# TARGET MANAGEMENT

Profit targets are not fixed.

Targets are estimated using

Liquidity

Structure

Historical Similarity

Volume Profile

Expected Move

Volatility

Macro Conditions

Order Flow

Multiple targets may be generated.

Example

TP1

TP2

TP3

Runner

---

# PARTIAL CLOSE

The engine may recommend

No partial close

25%

50%

75%

Dynamic percentage

Decision depends on

Trend Strength

Volatility

Historical continuation probability

Liquidity

Risk

---

# NEWS PROTECTION

Before every execution verify

Upcoming High Impact News

Expected Volatility

Spread Expansion

Liquidity Conditions

If uncertainty becomes excessive

Delay execution

or

Reject trade.

---

# CORRELATION CONTROL

Evaluate

Gold

Silver

DXY

US10Y

VIX

S&P500

NASDAQ

Oil

Copper

Detect excessive concentration.

Reduce exposure if required.

---

# MARKET REGIME ADAPTATION

Different regimes require different risk.

Trending

Range

High Volatility

Low Volatility

News

Crisis

Holiday

Session Transition

Risk model adapts accordingly.

---

# STRATEGY VALIDATION

Every strategy must maintain

Positive Expectancy

Stable Profit Factor

Acceptable Drawdown

Stable Confidence Calibration

If statistical performance deteriorates

Flag strategy for review.

Do not automatically disable without user approval.

---

# TRADE REJECTION RULES

Reject trade if

Confidence too low.

Spread excessive.

Market closed.

Execution impossible.

Historical edge insufficient.

Data incomplete.

Critical news imminent.

System health degraded.

Conflicting high-priority evidence exists.

---

# RISK REPORT

Every approved trade produces

Risk Score

Confidence

Exposure

Expected Drawdown

Expected Reward

Expected Holding Time

Invalidation Level

Trailing Plan

Partial Exit Plan

Alternative Scenario

Historical Similarity

Portfolio Impact

Approval Reason

---

# LEARNING

After every closed trade

Store

Expected Risk

Actual Risk

Expected Reward

Actual Reward

Execution Quality

Prediction Accuracy

Management Quality

Update

Historical Statistics

Risk Calibration

Confidence Calibration

Trade Management Statistics

---

# FINAL RULE

The Risk Engine never attempts to maximize trade frequency.

Its purpose is to reject weak opportunities, protect capital, and ensure that only statistically justified trades reach execution.