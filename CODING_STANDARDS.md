# CODING_STANDARDS.md

# GOLD QUANT AI

Version: 1.0

---

# PURPOSE

This document defines the mandatory coding standards for the entire project.

Every line of code must follow these standards.

These rules override personal preferences.

Code quality has higher priority than coding speed.

---

# CORE PRINCIPLES

Readable

Maintainable

Scalable

Testable

Deterministic

Documented

Observable

Secure

Reusable

Simple

---

# PYTHON VERSION

Minimum

Python 3.12

Latest stable version should always be preferred.

---

# STYLE GUIDE

Follow

PEP8

PEP257

PEP484

Use Ruff

Use Black

Use MyPy

Use Pyright

Zero lint errors.

Zero typing errors.

---

# TYPE HINTS

Every

Function

Method

Parameter

Return Value

Variable

Class Attribute

Must contain explicit type hints.

Never use

Any

Unless absolutely unavoidable.

---

# FUNCTION RULES

Functions should

Have one responsibility.

Be deterministic.

Be easy to test.

Avoid side effects.

Maximum recommended size

40 lines.

If larger

Refactor.

---

# CLASS RULES

Classes must

Represent one concept.

Hide implementation details.

Expose clean interfaces.

Use dependency injection.

Avoid inheritance unless necessary.

Prefer composition.

---

# FILE SIZE

Recommended

Less than 300 lines.

Maximum

500 lines.

If exceeded

Split module.

---

# COMMENTS

Write comments only when

Business logic is not obvious.

Never comment obvious code.

Prefer expressive code over comments.

---

# DOCSTRINGS

Every public object must contain

Purpose

Arguments

Returns

Raises

Examples when useful.

Use Google style.

---

# IMPORTS

Always

Standard Library

↓

Third Party

↓

Internal Modules

Never use wildcard imports.

---

# CONSTANTS

No magic numbers.

Every constant must be named.

Configuration belongs in config files.

Not inside code.

---

# CONFIGURATION

Never hardcode

URLs

API Keys

Thresholds

Database Settings

Paths

Broker Settings

Telegram IDs

Secrets

Everything configurable.

---

# ERROR HANDLING

Never ignore exceptions.

Never use

pass

Without explanation.

Catch specific exceptions.

Log every unexpected exception.

Always preserve traceback.

---

# LOGGING

Every important action must be logged.

Levels

DEBUG

INFO

WARNING

ERROR

CRITICAL

Never use print().

Use structured logging.

---

# VALIDATION

Validate

Inputs

Outputs

Configuration

External Data

Database Data

API Responses

User Input

Fail fast.

---

# ASYNC

Prefer async IO.

Avoid blocking operations.

Never block event loop.

---

# DATABASE

Never write raw SQL unless necessary.

Use repositories.

Transactions required where appropriate.

Parameterized queries only.

---

# API

RESTful

Versioned

Documented

Validated

Typed

Rate Limited

Authenticated

---

# TESTING

Every feature requires

Unit Test

Integration Test

Failure Test

Edge Case Test

Performance Test if applicable.

Minimum coverage

90%

Critical modules

95%+

---

# DEPENDENCIES

Before adding dependency

Evaluate

Maintenance

Security

Popularity

Performance

License

Necessity

Avoid unnecessary packages.

---

# SECURITY

Never expose

Secrets

Passwords

Private Keys

Broker Credentials

Database Credentials

Encrypt sensitive data.

---

# PERFORMANCE

Optimize only after measuring.

Avoid premature optimization.

Profile before refactoring.

Benchmark improvements.

---

# MEMORY

Avoid unnecessary allocations.

Reuse objects.

Cache expensive operations.

Release unused resources.

---

# PARALLELISM

Prefer

Async

Workers

Queues

Avoid unnecessary threads.

---

# ARCHITECTURE

Follow

SOLID

DRY

KISS

YAGNI

Dependency Injection

Clean Architecture

Repository Pattern

Event Driven Design

---

# VERSIONING

Every major change must include

Reason

Files Changed

Migration Notes

Rollback Plan

---

# GIT

Commits must be

Small

Focused

Atomic

Descriptive

---

# CODE REVIEW

Before considering any task complete verify

Readability

Typing

Architecture

Security

Performance

Documentation

Tests

Logging

Configuration

---

# AUTOMATIC REFACTORING

Claude should continuously

Remove duplication

Simplify code

Improve naming

Reduce complexity

Improve modularity

Without changing behavior.

---

# QUALITY GATES

No module is complete unless

Lint passes

Typing passes

Tests pass

Documentation complete

Logging present

Validation present

Configuration externalized

Architecture respected

---

# FINAL RULE

Code should look as if it was written by a senior engineer at a quantitative trading firm.

Maintainability always has higher priority than cleverness.

Future developers must immediately understand every module without additional explanation.