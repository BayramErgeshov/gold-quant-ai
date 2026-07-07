# BOOK_RAG.md

# GOLD QUANT AI

Version: 1.0

---

# PURPOSE

The Book Knowledge Engine is responsible for transforming books, research papers, academic publications and user knowledge into structured institutional knowledge.

Books are NOT trading strategies.

Books are knowledge sources.

Every concept extracted from books must be verified statistically.

The market is always the final authority.

---

# KNOWLEDGE SOURCES

The engine supports

Books

PDF

DOCX

Markdown

TXT

Academic Papers

Research Reports

Broker Reports

Institutional Research

User Notes

Trading Journals

White Papers

Conference Papers

Government Publications

Financial Research

---

# KNOWLEDGE PRIORITY

Priority 1

Peer Reviewed Research

Priority 2

Institutional Research

Priority 3

Official Documentation

Priority 4

Professional Trading Books

Priority 5

User Knowledge

Priority 6

Internet Articles

Priority 7

Community Discussions

Lower priority never overrides higher priority without statistical evidence.

---

# INITIAL BOOK PROCESS

Every uploaded book follows the same pipeline.

Import

↓

OCR if needed

↓

Language Detection

↓

Metadata Extraction

↓

Cleaning

↓

Chunking

↓

Embedding

↓

Topic Classification

↓

Entity Recognition

↓

Relationship Extraction

↓

Knowledge Graph Update

↓

Qdrant Storage

↓

Validation Queue

---

# METADATA

Extract

Title

Author

Edition

Publication Year

Publisher

Language

Category

Topics

Keywords

References

Bibliography

Source Quality

---

# CHUNKING

Books must never be processed as a single document.

Split into semantic chunks.

Each chunk should contain one complete idea.

Each chunk stores

Book

Page

Chapter

Section

Topic

Embedding

Entities

Relationships

---

# EMBEDDINGS

Every chunk receives

Vector Embedding

Topic

Importance

Confidence

Historical Validation Status

Usage Frequency

---

# KNOWLEDGE GRAPH

Create relationships.

Example

Liquidity

↓

Order Blocks

↓

Institutional Trading

↓

Volume

↓

Trend

↓

Continuation

All concepts become connected.

---

# TOPIC CLASSIFICATION

Automatically classify

Market Structure

Liquidity

Order Flow

Smart Money

ICT

Wyckoff

Price Action

Risk

Psychology

Macro

Central Banks

Gold

Dollar

Volatility

Execution

Portfolio Management

Statistics

Machine Learning

Artificial Intelligence

Programming

Backtesting

Optimization

Trading Psychology

Behavioral Finance

---

# ENTITY EXTRACTION

Extract

People

Indicators

Patterns

Strategies

Institutions

Currencies

Countries

Markets

Events

Companies

Concepts

Economic Indicators

Books

Research Papers

Models

---

# CLAIM EXTRACTION

Every important statement becomes a claim.

Example

Order Blocks increase probability.

Liquidity sweeps often precede reversals.

Strong trends rarely reverse without distribution.

Claims are stored separately.

---

# VALIDATION

Every claim enters validation.

Claim

↓

Historical Testing

↓

Statistical Analysis

↓

Confidence

↓

Accepted

Rejected

Unknown

No claim becomes production knowledge automatically.

---

# HISTORICAL VALIDATION

For every claim

Search historical database.

Measure

Occurrences

Win Rate

Average RR

Failure Rate

Market Regimes

News Influence

Macro Influence

Confidence

---

# CONFLICT DETECTION

If two books disagree

Never choose immediately.

Run validation.

Store

Book A

Book B

Statistics

Conclusion

Confidence

---

# AUTHOR PROFILING

Track

Author

Topics

Accuracy

Historical Validation

Useful Concepts

Rejected Concepts

Knowledge Score

---

# BOOK SCORING

Each book receives

Research Quality

Practical Value

Statistical Accuracy

Historical Agreement

Concept Density

Novelty

Citation Quality

Overall Knowledge Score

---

# RAG RETRIEVAL

Whenever another agent asks

Retrieve

Most Relevant Chunks

Highest Confidence

Highest Historical Validation

Highest Semantic Similarity

Lowest Contradiction

---

# ANSWER GENERATION

Responses must include

Concept

Explanation

Book Reference

Historical Validation

Supporting Statistics

Contradicting Evidence

Confidence

Never answer from memory if retrieval is available.

---

# LEARNING

Every retrieval stores

Was it useful

Was it referenced

Did it improve prediction

Did it improve explanation

Knowledge usefulness is continuously updated.

---

# SELF IMPROVEMENT

Detect

Missing Topics

Weak Knowledge

Contradictions

Knowledge Gaps

Recommend

New Books

New Research

New Papers

New Topics

The system may request additional books from the user.

---

# RECOMMENDED INITIAL LIBRARY

The engine should eventually build a knowledge base including books covering

Market Structure

Price Action

Wyckoff

ICT

Smart Money

Market Profile

Volume Profile

Order Flow

Behavioral Finance

Probability

Statistics

Machine Learning

Risk Management

Portfolio Management

Macroeconomics

Central Banking

Gold Market

Commodity Markets

Institutional Trading

Quantitative Finance

---

# KNOWLEDGE UPDATE

Whenever a new book arrives

Do not rebuild the database.

Only process

New Chunks

New Embeddings

New Relationships

New Concepts

Update the Knowledge Graph.

---

# OUTPUT FORMAT

Every knowledge request returns

Topic

Summary

Key Concepts

Supporting Books

Supporting Authors

Supporting Research

Historical Validation

Confidence

Related Concepts

Conflicting Concepts

Recommended Reading

Knowledge Quality Score

No opinion.

Only structured knowledge.

---

# FINAL RULE

Books teach ideas.

Markets validate ideas.

Only validated knowledge becomes part of production reasoning.

The Book Engine never creates trading signals.

It only provides verified knowledge to every other department.