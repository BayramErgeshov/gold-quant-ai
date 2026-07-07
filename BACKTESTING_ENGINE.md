# BACKTESTING_ENGINE.md

# GOLD QUANT AI

Version: 1.0

---

# PURPOSE

The Backtesting Engine is responsible for validating every hypothesis before it reaches production.

No strategy.

No parameter.

No machine learning model.

No indicator.

No weighting.

No execution logic.

May enter production without passing the complete validation pipeline.

Historical validation is mandatory.

---

# CORE PRINCIPLES

Backtests must be reproducible.

Backtests must be deterministic.

Backtests must use historical data only.

No future information may leak into the past.

No look-ahead bias.

No survivorship bias.

No curve fitting.

No overfitting.

No manual intervention during execution.

---

# DATA REQUIREMENTS

Historical data must include

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

Session

Timezone

News Events

Macro Events

DXY

US10Y

ETF

COT

Volatility

---

# DATA VALIDATION

Before every backtest verify

Missing Candles

Duplicate Candles

Incorrect Prices

Timezone

Spread Quality

Historical Integrity

Data Consistency

Outliers

Corrupted Records

---

# BACKTEST MODES

Historical Replay

Bar Replay

Tick Replay

Monte Carlo

Walk Forward

Cross Validation

Stress Testing

Parameter Optimization

Market Regime Testing

---

# TEST TYPES

Strategy Test

Signal Test

Execution Test

Risk Test

ML Test

Macro Test

News Test

Pattern Test

Agent Test

Portfolio Test

---

# MARKET REGIMES

Every strategy must be tested in

Bull Markets

Bear Markets

Ranges

Accumulation

Distribution

High Volatility

Low Volatility

News Periods

Central Bank Events

Financial Crisis

Pandemic

War

Flash Crash

Holiday Sessions

---

# TIME PERIODS

Minimum validation should include

Multiple years

Multiple volatility regimes

Multiple macro cycles

Multiple monetary policy cycles

Never validate using one market condition only.

---

# EXECUTION SIMULATION

Simulate

Spread

Slippage

Commission

Swap

Latency

Execution Delay

Partial Fill

Rejected Orders

Broker Limitations

---

# RISK SIMULATION

Simulate

Protective Stop

Trailing Stop

Break Even

Partial Close

Dynamic Targets

Position Size

Maximum Exposure

Portfolio Risk

---

# METRICS

Calculate

Win Rate

Loss Rate

Expectancy

Profit Factor

Sharpe Ratio

Sortino Ratio

Calmar Ratio

Recovery Factor

Maximum Drawdown

Average Drawdown

Average Win

Average Loss

Average RR

Maximum Consecutive Wins

Maximum Consecutive Losses

Average Holding Time

Trade Frequency

Capital Growth

Equity Curve

Confidence Calibration

Prediction Accuracy

Execution Quality

---

# TRADE ANALYSIS

For every trade store

Entry

Exit

Reason

Structure

Liquidity

Trend

Macro

News

Historical Similarity

Expected Move

Actual Move

Maximum Favorable Excursion

Maximum Adverse Excursion

Management Quality

---

# PARAMETER TESTING

Test

Indicator Settings

Risk Parameters

Confidence Thresholds

Weighting

Execution Logic

Trailing Logic

Target Logic

Never optimize only for maximum profit.

Optimize for robustness.

---

# ROBUSTNESS TEST

Evaluate

Different Brokers

Different Spread

Different Slippage

Different Sessions

Different Years

Different Volatility

Different Market Regimes

Small Data Changes

Random Trade Removal

Random Execution Delay

---

# WALK FORWARD

Split

Training Data

↓

Validation Data

↓

Out-of-Sample Data

↓

Forward Simulation

Only strategies passing every stage continue.

---

# MONTE CARLO

Randomize

Trade Order

Slippage

Spread

Execution Delay

Market Noise

Measure

Stability

Drawdown

Risk

Confidence

---

# OVERFITTING DETECTION

Measure

Parameter Sensitivity

Feature Stability

Prediction Stability

Generalization

Reject strategies that perform well only on one dataset.

---

# STRATEGY COMPARISON

Compare

Strategy A

Strategy B

Strategy C

Current Production

Evaluate

Profit

Risk

Drawdown

Consistency

Confidence

Robustness

---

# FAILURE ANALYSIS

For every failed strategy determine

Why it failed

Which market regime

Which feature failed

Which assumptions failed

Can it be improved

Should it be archived

---

# SUCCESS ANALYSIS

For every successful strategy determine

Why it worked

Which features contributed

Which conditions required

Can it generalize

Can confidence improve

---

# REPORT

Every completed backtest generates

Strategy Name

Version

Period Tested

Markets

Trades

Win Rate

Profit Factor

Sharpe

Sortino

Drawdown

Expectancy

Confidence Calibration

Historical Robustness

Strengths

Weaknesses

Failure Conditions

Recommended Improvements

Production Recommendation

---

# APPROVAL

A strategy may enter production only if

Historical Validation Passed

Walk Forward Passed

Monte Carlo Passed

Robustness Passed

Risk Validation Passed

User Approved

---

# ARCHIVING

Every completed backtest remains stored.

Nothing is deleted.

Every result remains searchable.

Every version remains reproducible.

---

# FINAL RULE

The Backtesting Engine exists to protect the platform from false confidence.

No idea becomes production logic until it has demonstrated robust statistical performance across multiple market conditions and validation methods.