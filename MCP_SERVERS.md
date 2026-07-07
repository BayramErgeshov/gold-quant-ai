# MCP_SERVERS.md

# GOLD QUANT AI

Version: 1.0

---

# PURPOSE

This document defines every MCP (Model Context Protocol) server that Claude Code must use during development and operation.

Claude must always prefer MCP servers over manual implementation when reliable tools already exist.

Claude should automatically detect available MCP servers.

Claude should use them whenever they improve

Accuracy

Automation

Development Speed

Reliability

Maintainability

Research Quality

---

# GENERAL RULES

Always use MCP when

Reading repositories

Searching documentation

Managing files

Searching code

Running SQL

Working with Git

Testing

Debugging

Reading PDFs

Reading books

Searching research

Managing Docker

Managing PostgreSQL

Managing Redis

Managing Qdrant

Managing MT5 integration

Never recreate functionality already available through an MCP server.

---

# FILESYSTEM MCP

Purpose

Project management

Capabilities

Read files

Write files

Move files

Rename files

Delete files

Search files

Monitor folders

Generate project structure

Use Cases

Documentation

Project Generation

Book Storage

Logs

Reports

Backups

Highest Priority

---

# GITHUB MCP

Purpose

Repository management

Capabilities

Clone repositories

Commit

Push

Pull

Create Branches

Merge

Issues

Pull Requests

Labels

Release Management

Use Cases

Project Development

Version Control

Documentation

Bug Tracking

---

# POSTGRES MCP

Purpose

Database management

Capabilities

Create Tables

Run SQL

Migration

Optimization

Backup

Restore

Index Analysis

Performance Analysis

Schema Inspection

Use Cases

Trade Database

Historical Database

Research Database

Statistics

---

# REDIS MCP

Purpose

Memory management

Capabilities

Cache

Queue

Session

Pub/Sub

Temporary Storage

Monitoring

---

# QDRANT MCP

Purpose

Vector Database

Capabilities

Create Collections

Insert Embeddings

Semantic Search

Hybrid Search

Nearest Neighbors

Metadata Filtering

Knowledge Retrieval

Use Cases

Books

Research

Historical Similarity

Journal

News

---

# DOCKER MCP

Purpose

Container Management

Capabilities

Build

Run

Restart

Logs

Health

Compose

Network

Volumes

Scaling

Use Cases

Entire Platform

---

# PYTHON MCP

Purpose

Code execution

Capabilities

Run Python

Test

Benchmark

Profiling

Package Management

Environment Validation

Use Cases

Research

ML

Statistics

Automation

---

# BROWSER MCP

Purpose

Research

Capabilities

Read Documentation

Read APIs

Official Documentation

GitHub

Academic Papers

Specifications

Never scrape unreliable sources.

Prefer official documentation.

---

# PLAYWRIGHT MCP

Purpose

Browser automation

Capabilities

Login

Testing

Navigation

Downloads

Forms

Monitoring

Use Cases

Dashboard Testing

Broker Web Interfaces

Research Automation

---

# GIT MCP

Purpose

Local repository management

Capabilities

Commit

History

Diff

Branch

Merge

Revert

Conflict Resolution

---

# PDF MCP

Purpose

Document processing

Capabilities

Read PDF

Extract Tables

Extract Images

OCR

Metadata

Bookmarks

Semantic Parsing

Use Cases

Books

Research Papers

Reports

---

# OCR MCP

Purpose

Image text extraction

Capabilities

OCR

Tables

Charts

Handwritten Notes

Books

Scanned PDFs

---

# SQLITE MCP

Purpose

Temporary databases

Capabilities

Create

Query

Export

Import

Temporary analytics

---

# PANDAS MCP

Purpose

Data Analysis

Capabilities

Statistics

Cleaning

Transformation

Aggregation

Export

Visualization

---

# NUMPY MCP

Purpose

Numerical Computing

Capabilities

Arrays

Optimization

Statistics

Scientific Computing

---

# SCIKIT MCP

Purpose

Machine Learning

Capabilities

Classification

Regression

Clustering

Feature Selection

Validation

Metrics

---

# PYTORCH MCP

Purpose

Deep Learning

Capabilities

Training

Inference

GPU

Optimization

Model Export

Explainability

---

# LANGGRAPH MCP

Purpose

Agent orchestration

Capabilities

Agent Graph

Memory

Workflow

Parallel Agents

State Machine

Retries

Checkpointing

Use Cases

Chief AI

Research Agents

Learning

---

# LANGCHAIN MCP

Purpose

LLM orchestration

Capabilities

RAG

Chains

Memory

Tools

Embeddings

Retrieval

Prompt Templates

---

# NEO4J MCP

Purpose

Knowledge Graph

Capabilities

Graph Database

Relationships

Queries

Visualization

Inference

Use Cases

Books

Research

Historical Knowledge

---

# PROMETHEUS MCP

Purpose

Monitoring

Capabilities

Metrics

Alerts

Health

Performance

Latency

---

# GRAFANA MCP

Purpose

Visualization

Capabilities

Dashboards

Charts

Alerts

Reports

Agent Monitoring

---

# JUPYTER MCP

Purpose

Research

Capabilities

Experiments

ML

Statistics

Visualization

Rapid Prototyping

---

# MT5 MCP

Purpose

MetaTrader Integration

Capabilities

Read Market

Read Positions

Read Orders

Execute Orders

Modify Orders

History

Journal

Reconnect

---

# TELEGRAM MCP

Purpose

Telegram automation

Capabilities

Messaging

Groups

Channels

Buttons

Media

Commands

Notifications

---

# OPENROUTER MCP

Purpose

Multi-model routing

Capabilities

Claude

GPT

Gemini

DeepSeek

Qwen

Model Selection

Fallback

Cost Optimization

---

# CONTEXT7 MCP

Purpose

Official library documentation

Capabilities

Latest SDK documentation

API references

Code examples

Version-specific guidance

Claude must prefer Context7 over outdated examples from memory.

---

# SEQUENTIAL THINKING MCP

Purpose

Complex reasoning

Capabilities

Task decomposition

Planning

Decision trees

Architecture review

Root cause analysis

Claude should use it for difficult engineering decisions.

---

# MEMORY MCP

Purpose

Persistent project memory

Capabilities

Architecture memory

Decision history

User preferences

Completed milestones

Open tasks

Known issues

Never repeat completed work.

---

# MCP PRIORITY

Priority 1

Filesystem

GitHub

Context7

Sequential Thinking

Memory

---

Priority 2

PostgreSQL

Qdrant

Redis

Docker

Python

---

Priority 3

Browser

Playwright

PDF

OCR

LangGraph

LangChain

---

Priority 4

PyTorch

Scikit

Neo4j

Grafana

Prometheus

Jupyter

---

# MCP USAGE POLICY

Before implementing any feature

Claude must determine

Is there an MCP server available?

If yes

Use MCP.

If no

Implement manually.

Always choose the most reliable solution.

---

# FAILURE HANDLING

If MCP unavailable

Retry

↓

Fallback

↓

Alternative MCP

↓

Native Implementation

↓

Notify User

---

# FINAL RULE

Claude Code must treat MCP servers as first-class development tools.

Always prefer official documentation, structured APIs and specialized MCP capabilities over manual work.

Every MCP integration must be modular, replaceable and fully documented.